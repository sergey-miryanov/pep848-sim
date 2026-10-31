from collections import Counter
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collectors.collector import Collector
from pep848_sim.collectors.heap import Heap
from pep848_sim.structures import (
    AMAZON0302_HEAD,
    AMAZON0302_SIZE,
    TASK_GROUPS_HEAD,
    TASK_GROUPS_PATH,
    TASK_GROUPS_SIZE,
    Amazon0302,
    Build,
    Chains,
    Graph,
    Hierarchy,
    Own,
    Rings,
    Root,
    Shape,
    StructureParameters,
    TaskGroups,
    Tree,
)
from test_heap import reachable


def long_lived(shape: Shape, size: int, root: Root) -> StructureParameters:
    return StructureParameters(
        shape=shape,
        size=size,
        root=root,
        lifetime=None,
        rebuild_interval=None,
        build_churn=0,
    )


# A shape of a reader's own: each object and the one before it hold each other.
DOUBLY_LINKED = """\
def links(i):
    if not i:
        return []
    return [(i - 1, i), (i, i - 1)]
"""


def own_table(table: dict[int, list[tuple[int, int]]]) -> Own:
    """A shape of a reader's own that looks each object's links up in a table."""
    return Own(f"TABLE = {table!r}\ndef links(i):\n    return TABLE.get(i, [(0, i)])\n")


@st.composite
def own_shapes(draw: st.DrawFn) -> Own:
    """Shapes of a reader's own: an earlier object holds each new object, and a
    few more links join any two of the objects built so far. Past the table's 40
    objects, the first object holds each."""
    table = {0: draw(st.lists(st.just((0, 0)), max_size=1))}
    for i in range(1, 40):
        holder = draw(st.integers(0, i - 1))
        pair = st.tuples(st.integers(0, i), st.integers(0, i))
        table[i] = [(holder, i), *draw(st.lists(pair, max_size=2))]
    return own_table(table)


def built(heap: Heap, parameters: StructureParameters) -> Build:
    build = Build(heap, parameters)
    while not build.done:
        build.add()
    return build


@pytest.mark.parametrize("root", ["module", "frame"])
def test_a_dropped_tree_with_parent_pointers_becomes_cyclic_garbage(
    root: Root,
) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Tree(), 7, root))

    build.drop()

    assert heap.uncollected_garbage == 7
    assert len(set(collector.nursery) - reachable(heap)) == 7


def test_a_structure_sys_holds_hangs_off_it_from_its_first_object() -> None:
    heap = Heap(Collector())
    build = Build(heap, long_lived(Chains(width=2), 3, "module"))

    build.add()

    assert heap.references(heap.module_root) == (1,)
    assert heap.frame_roots() == {}


def test_a_structure_built_in_a_frame_hangs_off_sys_once_its_build_ends() -> None:
    heap = Heap(Collector())
    parameters = StructureParameters(
        shape=Chains(width=2),
        size=3,
        root="module",
        lifetime=None,
        rebuild_interval=None,
        build_churn=0,
        built_in_frame=True,
    )
    build = built(heap, parameters)
    # The frame that builds it holds its root, as a module-level X = build() holds
    # what build() makes until it returns.
    assert heap.references(heap.module_root) == ()
    assert heap.frame_roots() == {1: 1}

    build.finish()

    assert heap.references(heap.module_root) == (1,)
    assert heap.frame_roots() == {}


def test_a_structure_a_frame_holds_is_built_in_one_already() -> None:
    with pytest.raises(ValueError, match="built in one already"):
        StructureParameters(Tree(), 3, "frame", None, None, 0, built_in_frame=True)


def test_a_lone_tree_root_lies_on_no_cycle_and_goes_on_the_spot() -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Tree(), 1, "frame"))

    build.drop()

    assert heap.uncollected_garbage == 0
    assert list(collector.nursery) == [heap.module_root]


@pytest.mark.parametrize("shape", [Chains(width=3), Hierarchy(branches=3)])
@pytest.mark.parametrize("root", ["module", "frame"])
def test_refcounting_frees_a_dropped_shape_without_cycles_on_the_spot(
    shape: Shape, root: Root
) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(shape, 10, root))

    build.drop()

    assert heap.uncollected_garbage == 0
    assert list(collector.nursery) == [heap.module_root]


def test_chains_put_each_new_object_on_the_next_chain_in_turn() -> None:
    collector = Collector()
    heap = Heap(collector)
    build = Build(heap, long_lived(Chains(width=2), 6, "module"))

    for _ in range(6):
        assert not build.done
        build.add()

    assert build.done
    root, a, b, c, d, e = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, a, b, c, d, e)] == [
        (a, b),
        (c,),
        (d,),
        (e,),
        (),
        (),
    ]
    assert heap.references(heap.module_root) == (root,)
    assert heap.frame_roots() == {}
    assert heap.clock == 6


def test_a_tree_links_each_object_and_its_parent_both_ways() -> None:
    collector = Collector()
    heap = Heap(collector)

    built(heap, long_lived(Tree(), 5, "frame"))

    root, a, b, c, d = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, a, b, c, d)] == [
        (a, b),
        (root, c, d),
        (root,),
        (a,),
        (a,),
    ]
    assert heap.references(heap.module_root) == ()
    assert heap.frame_roots() == {root: 1}
    assert heap.clock == 5


def test_a_hierarchy_links_each_object_from_its_parent_alone() -> None:
    collector = Collector()
    heap = Heap(collector)

    built(heap, long_lived(Hierarchy(branches=3), 6, "frame"))

    root, a, b, c, d, e = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, a, b, c, d, e)] == [
        (a, b, c),
        (d, e),
        (),
        (),
        (),
        (),
    ]
    assert heap.references(heap.module_root) == ()
    assert heap.frame_roots() == {root: 1}
    assert heap.clock == 6


def test_a_hierarchy_without_branches_is_refused() -> None:
    with pytest.raises(ValueError, match="ends at its root"):
        Hierarchy(branches=0)


def test_a_graph_shares_each_edge_with_a_node_read_anywhere_before() -> None:
    collector = Collector()
    heap = Heap(collector)

    built(heap, long_lived(Graph(edges=2), 11, "module"))

    # Three nodes are too few to spread over: b's and c's edges both fall to a.
    root, f, a, a1, a2, b, b1, b2, c, c1, c2 = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, f, a, b, c)] == [
        (f, a, b, c),
        (root,),
        (a1, a2, b1, b2, c1, c2),
        (b1, b2),
        (c1, c2),
    ]
    assert all(heap.references(x) == () for x in (a1, a2, b1, b2, c1, c2))
    assert heap.references(heap.module_root) == (root,)


def test_a_late_nodes_edges_reach_back_across_the_whole_graph() -> None:
    graph = Graph(edges=2)
    # Nodes 9,000 to 9,999: the nodes their edges share, by number.
    span = 3
    shared = [
        (source - 2) // span
        for i in range(2 + 9_000 * span, 2 + 10_000 * span)
        for source, _ in graph.links(i)[1:]
    ]
    assert len(shared) == 2_000
    assert min(shared) < 500
    assert max(shared) > 8_500
    assert sum(node < 4_500 for node in shared) > 800


def test_amazon0302s_dict_takes_graph_and_node_over_from_g() -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Amazon0302(), AMAZON0302_HEAD, "frame"))
    g, graph, node, dict_, cache, adj = list(collector.nursery)[1:]

    assert heap.references(g) == (dict_,)
    assert heap.references(dict_) == (graph, node, cache, adj)
    assert build.done


def test_amazon0302s_objects_hang_off_adj_node_or_their_endpoints() -> None:
    shape = Amazon0302()
    adj, node = AMAZON0302_HEAD - 1, 2
    kinds: Counter[str] = Counter()
    for i in range(AMAZON0302_HEAD, AMAZON0302_SIZE):
        holders = [source for source, _ in shape.links(i)]
        assert all(source < i for source in holders)
        if holders == [adj]:
            kinds["adjacency"] += 1
        elif holders == [node]:
            kinds["attributes"] += 1
        else:
            # An edge hangs off one or two objects that stand for adjacency dicts.
            assert all(h == adj or shape.links(h) == [(adj, h)] for h in holders)
            kinds["edge"] += 1
    # The file's 262,111 nodes, two dicts each, and its 899,792 edges, one in 16:
    # taking every 16th object of read_adjlist's order lands within 2% of that.
    assert kinds["adjacency"] == pytest.approx(262_111 / 16, rel=0.02)
    assert kinds["attributes"] == pytest.approx(262_111 / 16, rel=0.02)
    assert kinds["edge"] == pytest.approx(899_792 / 16, rel=0.02)


def test_a_larger_amazon0302_repeats_the_files_pattern() -> None:
    shape = Amazon0302()
    body = AMAZON0302_SIZE - AMAZON0302_HEAD
    for i in range(AMAZON0302_HEAD, AMAZON0302_HEAD + 1_000):
        once, again = shape.links(i), shape.links(i + body)
        if once[0][0] < AMAZON0302_HEAD:
            assert again == [(s, t + body) for s, t in once]
        else:
            assert again == [(s + body, t + body) for s, t in once]


def test_task_groups_loop_holds_its_ready_queue_and_timers_down_a_path() -> None:
    collector = Collector()
    heap = Heap(collector)
    built(heap, long_lived(TaskGroups(), TASK_GROUPS_HEAD, "frame"))

    objects = list(collector.nursery)[1:]
    *path, loop, ready, timers = objects

    assert [heap.references(x) for x in path] == [(x,) for x in [*path[1:], loop]]
    assert heap.references(loop) == (ready, timers)
    assert len(path) == TASK_GROUPS_PATH


def test_a_tasks_handle_leaves_the_ready_queue_as_the_task_runs() -> None:
    collector = Collector()
    heap = Heap(collector)
    build = Build(heap, long_lived(TaskGroups(), TASK_GROUPS_HEAD + 8, "frame"))
    # The root task's 7 objects, its handle the fifth.
    for _ in range(TASK_GROUPS_HEAD + 7):
        build.add()
    ready = list(collector.nursery)[TASK_GROUPS_HEAD - 1]
    handle = list(collector.nursery)[TASK_GROUPS_HEAD + 5]

    assert heap.references(ready) == (handle,)

    # Its TaskGroup, the first object the task makes as it runs.
    build.add()

    assert heap.references(ready) == ()


def test_a_task_tree_keeps_13_objects_a_task_and_14_a_leaf_and_drops_clean() -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(TaskGroups(), TASK_GROUPS_SIZE, "frame"))
    *_, ready, timers = list(collector.nursery)[1 : TASK_GROUPS_HEAD + 1]

    # 55,987 tasks, 16 to a group: 584 groups of tasks that start TaskGroups and
    # 2,916 of leaves. Each task's handle and its TaskStepMethWrapper went with
    # the ready queue's hold on them.
    assert heap.references(ready) == ()
    assert len(heap.references(timers)) == 2_916
    assert len(reachable(heap)) - 1 == TASK_GROUPS_HEAD + 13 * 584 + 14 * 2_916

    build.drop()

    assert heap.uncollected_garbage == 0
    assert set(collector.nursery) <= reachable(heap)


def test_a_larger_task_tree_starts_again_under_the_same_loop() -> None:
    shape = TaskGroups()
    tree = TASK_GROUPS_SIZE - TASK_GROUPS_HEAD

    def moved(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
        return [(s + tree if s >= TASK_GROUPS_HEAD else s, t + tree) for s, t in pairs]

    for i in range(TASK_GROUPS_HEAD, TASK_GROUPS_HEAD + 1_000):
        assert shape.links(i + tree) == moved(shape.links(i))
        assert shape.unlinks(i + tree) == moved(shape.unlinks(i))
    loop = TASK_GROUPS_PATH
    assert shape.links(TASK_GROUPS_HEAD + tree) == [(loop, TASK_GROUPS_SIZE)]


@pytest.mark.parametrize("size", [500, TASK_GROUPS_SIZE + 500])
def test_a_task_trees_teardown_cuts_only_links_among_its_objects(size: int) -> None:
    cuts = TaskGroups().teardown(size)

    assert cuts
    assert all(max(pair) < size for pair in cuts)
    assert TaskGroups().teardown(TASK_GROUPS_HEAD) == []


@pytest.mark.parametrize("root", ["module", "frame"])
def test_a_dropped_graph_stays_as_cyclic_garbage_with_its_roots_cycle(
    root: Root,
) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Graph(edges=2), 11, root))

    build.drop()

    assert heap.uncollected_garbage == 11
    assert len(set(collector.nursery) - reachable(heap)) == 11


def test_a_graph_whose_nodes_bring_fewer_than_no_edges_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot bring -1 edges"):
        Graph(edges=-1)


def test_rings_link_each_object_to_the_next_and_back_and_close() -> None:
    collector = Collector()
    heap = Heap(collector)

    built(heap, long_lived(Rings(length=3), 7, "frame"))

    root, a, b, c, d, e, f = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, a, b, c, d, e, f)] == [
        (a, d),
        (b, c),
        (a, c),
        (b, a),
        (e, f),
        (d, f),
        (e, d),
    ]
    assert heap.frame_roots() == {root: 1}
    assert heap.clock == 7


def test_a_ring_of_one_object_links_it_to_itself_both_ways() -> None:
    collector = Collector()
    heap = Heap(collector)

    built(heap, long_lived(Rings(length=1), 3, "frame"))

    root, a, b = list(collector.nursery)[1:]
    assert [heap.references(x) for x in (root, a, b)] == [(a, b), (a, a), (b, b)]


@pytest.mark.parametrize(("size", "garbage"), [(1, 0), (2, 0), (4, 3), (5, 3), (6, 5)])
def test_dropped_rings_stay_as_cyclic_garbage_but_a_lone_first_object(
    size: int, garbage: int
) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(Rings(length=3), size, "frame"))

    build.drop()

    # The list goes on the spot. A last ring of two links both ways and stays.
    assert heap.uncollected_garbage == garbage
    assert len(collector.nursery) == 1 + garbage


def test_a_ring_of_no_objects_is_refused() -> None:
    with pytest.raises(ValueError, match="a ring of 0 objects holds none"):
        Rings(length=0)


def test_a_build_that_outlasts_its_rebuild_interval_is_refused() -> None:
    def repeating(rebuild_interval: int) -> StructureParameters:
        # Ten objects, each followed by two churn allocations: a 30 kB build.
        return StructureParameters(
            shape=Tree(),
            size=10,
            root="frame",
            lifetime=20,
            rebuild_interval=rebuild_interval,
            build_churn=2,
        )

    repeating(30)
    with pytest.raises(ValueError, match="outlasts"):
        repeating(29)


def test_a_fraction_of_churn_spreads_over_the_builds_objects() -> None:
    chain = StructureParameters(
        shape=Chains(width=1),
        size=10,
        root="frame",
        lifetime=None,
        rebuild_interval=None,
        build_churn=Fraction(3, 4),
    )

    # By its k-th object a build has made 3k/4 churn allocations, rounded down.
    churn = [chain.churn_after(k) for k in range(1, 11)]
    assert churn == [0, 1, 1, 1, 0, 1, 1, 1, 0, 1]
    assert chain.build_length == 17


def test_a_whole_fraction_of_churn_reads_as_an_int() -> None:
    chain = StructureParameters(Chains(width=1), 2, "frame", None, None, Fraction(2))

    assert chain.build_churn == 2
    assert type(chain.build_churn) is int


@given(
    st.one_of(
        st.builds(Chains, width=st.integers(1, 8)),
        st.just(Tree()),
        st.builds(Hierarchy, branches=st.integers(1, 8)),
        st.builds(Graph, edges=st.integers(0, 4)),
        st.just(Amazon0302()),
        st.just(TaskGroups()),
        st.builds(Rings, length=st.integers(1, 8)),
        own_shapes(),
    ),
    st.integers(min_value=1, max_value=40),
    st.sampled_from(["module", "frame"]),
    st.data(),
)
def test_a_structure_keeps_the_counts_true_and_its_drop_counts_its_cycles(
    shape: Shape, size: int, root: Root, data: st.DataObject
) -> None:
    collector = Collector()
    heap = Heap(collector)
    build = Build(heap, long_lived(shape, size, root))

    for _ in range(data.draw(st.integers(min_value=0, max_value=size))):
        build.add()

    built_so_far = list(collector.nursery)[1:]
    frame_roots = {built_so_far[0]: 1} if root == "frame" and built_so_far else {}
    assert heap.frame_roots() == frame_roots
    held = Counter(t for x in collector.nursery for t in heap.references(x))
    held.update(frame_roots)
    held[heap.module_root] += 1  # the interpreter holds sys
    assert all(heap.reference_count(x) == held[x] for x in collector.nursery)

    while not build.done:
        build.add()
    build.drop()

    assert heap.uncollected_garbage == len(set(collector.nursery) - reachable(heap))


def test_an_own_shape_links_each_object_as_its_code_says() -> None:
    shape = Own(DOUBLY_LINKED)

    assert [shape.links(i) for i in range(3)] == [
        [],
        [(0, 1), (1, 0)],
        [(1, 2), (2, 1)],
    ]


def test_an_own_shape_without_links_calls_the_one_function_it_defines() -> None:
    shape = Own("from math import floor\n" + DOUBLY_LINKED.replace("links", "pairs"))

    assert shape.links(1) == [(0, 1), (1, 0)]
    with pytest.raises(ValueError, match=r"pairs\(1\) gives \(1, 2\)"):
        Own("def pairs(i):\n    return [(0, i), (i, i + 1)] if i else []\n").check(2)


def test_an_own_shape_counts_its_lines_from_where_its_code_starts() -> None:
    shape = Own("def links(i):\n    return 1 / 0\n", line=12)

    with pytest.raises(ValueError, match="raised ZeroDivisionError at line 13"):
        shape.links(0)
    with pytest.raises(ValueError, match="line 12 of your shape: expected ':'"):
        Own("def links(i)\n", line=12)


def test_a_dropped_own_shape_leaves_its_cycles_and_what_they_hold() -> None:
    # A list whose third object links back to the second: refcounting frees the
    # first two, and the cycle keeps the second and third and the two after.
    shape = own_table(
        {0: [], 1: [(0, 1)], 2: [(1, 2)], 3: [(2, 3), (3, 2)]}
        | {i: [(i - 1, i)] for i in (4, 5)}
    )
    collector = Collector()
    heap = Heap(collector)
    build = built(heap, long_lived(shape, 6, "frame"))

    build.drop()

    assert shape.cyclic_garbage(6) == heap.uncollected_garbage == 4


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("def links(i)\n    return []\n", "line 1 of your shape: expected ':'"),
        ("x = 1\n", r"your shape defines no links\(i\)"),
        (
            "def a(i):\n    return []\ndef b(i):\n    return []\n",
            r"your shape defines no links\(i\)",
        ),
        (
            "1 / 0\n",
            "your shape raised ZeroDivisionError at line 1: division by zero",
        ),
    ],
)
def test_own_code_that_defines_no_links_is_refused(code: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Own(code)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "return [(i, i + 1)]",
            r"links\(0\) gives \(0, 1\): a link joins two of objects 0 to 0",
        ),
        ("return [(-1, i)]", r"links\(0\) gives \(-1, 0\)"),
        ("return [(0.0, i)]", r"links\(0\) gives \(0.0, 0\)"),
        ("return [i]", r"links\(0\) gives \[0\], not \(source, target\) pairs"),
        ("return None", r"links\(0\) gives None, not \(source, target\) pairs"),
        (
            "return [(0, 0)]",
            r"links\(1\) gives object 1 no holder among objects 0 to 0",
        ),
        ("return [(i, i)]", r"links\(1\) gives object 1 no holder"),
        (
            "return 1 / 0",
            r"links\(0\) raised ZeroDivisionError at line 2: division by zero",
        ),
    ],
)
def test_a_link_the_heap_cannot_make_is_refused(body: str, message: str) -> None:
    shape = Own(f"def links(i):\n    {body}\n")

    # A check calls links(0) and links(1).
    with pytest.raises(ValueError, match=message):
        shape.check(2)


def test_a_check_refuses_links_that_answer_twice_differently() -> None:
    shape = Own(
        "calls = [0]\n"
        "def links(i):\n"
        "    calls[0] += 1\n"
        "    return [(0, i)] * (calls[0] % 2 + 1) if i else []\n"
    )

    with pytest.raises(ValueError, match=r"links\(1\) gave two answers"):
        shape.check(10)


def test_a_check_calls_only_the_first_objects_links() -> None:
    shape = Own("def links(i):\n    return [(0, i)] if i < 2000 else [(i, i + 1)]\n")

    shape.check(5000)
