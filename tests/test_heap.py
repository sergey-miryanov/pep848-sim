from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collector import Collector
from pep848_sim.heap import Heap


def new_heap() -> Heap:
    return Heap(Collector())


def reached_from(heap: Heap, starts: Iterable[int]) -> set[int]:
    """The tests' walk: the starts, and every object their references reach."""
    stack = list(starts)
    seen = set(stack)
    while stack:
        for target in heap.references(stack.pop()):
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def reachable(heap: Heap) -> set[int]:
    return reached_from(heap, [heap.module_root, *heap.frame_roots()])


@dataclass
class Built:
    collector: Collector = field(default_factory=Collector)
    heap: Heap = field(init=False)
    objects: list[int] = field(default_factory=list)
    # The test's own record of the frame roots, in the order taken.
    frame_roots: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.heap = Heap(self.collector)


@st.composite
def built_heaps(draw: st.DrawFn) -> Built:
    """A heap built by random allocations, links, and frame roots taken and let go."""
    built = Built()
    heap = built.heap
    built.objects.append(heap.module_root)
    for _ in range(draw(st.integers(min_value=0, max_value=60))):
        action = draw(st.sampled_from(["allocate", "grow", "link", "take", "let go"]))
        alive = st.sampled_from([x for x in built.objects if not heap.is_freed(x)])
        if action == "allocate":
            x = heap.allocate()
            built.objects.append(x)
            built.frame_roots[x] = 1  # the allocating frame holds it
        elif action == "grow":
            # As a workload builds a structure: the parent alone holds the child.
            parent = draw(alive)
            x = heap.allocate()
            built.objects.append(x)
            heap.link(parent, x)
            heap.let_go_frame_root(x)
        elif action == "link":
            heap.link(draw(alive), draw(alive))
        elif action == "take":
            x = draw(alive)
            heap.take_frame_root(x)
            built.frame_roots[x] = built.frame_roots.get(x, 0) + 1
        elif built.frame_roots:
            x = draw(st.sampled_from(list(built.frame_roots)))
            heap.let_go_frame_root(x)
            built.frame_roots[x] -= 1
            if not built.frame_roots[x]:
                del built.frame_roots[x]
    return built


def test_a_new_object_holds_no_references_and_its_allocating_frame_holds_it() -> None:
    heap = new_heap()

    x = heap.allocate()

    assert heap.references(x) == ()
    assert heap.reference_count(x) == 1
    assert heap.frame_roots() == {x: 1}


def test_each_allocation_is_a_different_object() -> None:
    heap = new_heap()

    assert heap.allocate() != heap.allocate()


def test_each_link_raises_the_count_of_its_target_a_repeat_included() -> None:
    heap = new_heap()
    x, y = heap.allocate(), heap.allocate()
    before = heap.reference_count(y)

    heap.link(x, y)
    heap.link(x, y)

    assert heap.reference_count(y) == before + 2


def test_an_object_lists_its_references_in_the_order_they_were_made() -> None:
    heap = new_heap()
    a, b, c = heap.allocate(), heap.allocate(), heap.allocate()

    heap.link(a, c)
    heap.link(a, b)
    heap.link(a, c)

    assert heap.references(a) == (c, b, c)


@given(built_heaps())
def test_an_objects_count_is_its_references_and_its_roots(built: Built) -> None:
    heap = built.heap
    held = Counter(target for x in built.objects for target in heap.references(x))
    held.update(built.frame_roots)
    held[heap.module_root] += 1  # the interpreter holds sys

    assert {x: heap.reference_count(x) for x in built.objects} == {
        x: held[x] for x in built.objects
    }


@given(built_heaps())
def test_the_heap_records_its_frame_roots_in_the_order_taken(built: Built) -> None:
    assert list(built.heap.frame_roots().items()) == list(built.frame_roots.items())


@given(built_heaps())
def test_refcounting_never_frees_a_reachable_object(built: Built) -> None:
    heap = built.heap

    assert [x for x in reachable(heap) if heap.is_freed(x)] == []


@given(built_heaps())
def test_what_refcounting_leaves_unreachable_hangs_off_a_cycle(built: Built) -> None:
    heap = built.heap
    alive = [x for x in built.objects if not heap.is_freed(x)]
    unreachable = set(alive) - reachable(heap)
    # Nothing reachable leads back to an unreachable object, so an unreachable
    # object that its own references reach lies on a cycle of unreachable ones.
    on_cycles = [x for x in unreachable if x in reached_from(heap, heap.references(x))]

    assert unreachable <= reached_from(heap, on_cycles)


@given(built_heaps())
def test_the_nursery_holds_each_alive_object_and_no_freed_one(built: Built) -> None:
    heap = built.heap

    assert list(built.collector.nursery) == [
        x for x in built.objects if not heap.is_freed(x)
    ]


def test_a_new_heaps_clock_reads_zero() -> None:
    assert new_heap().clock == 0


@given(st.lists(st.booleans(), max_size=60))
def test_the_clock_reads_the_kb_allocated_with_an_object_or_without(
    makes_object: list[bool],
) -> None:
    heap = new_heap()

    for make in makes_object:
        if make:
            heap.allocate()
        else:
            heap.allocate_unseen()

    assert heap.clock == len(makes_object)


def test_a_new_heap_has_the_module_root_held_by_the_interpreter() -> None:
    heap = new_heap()

    assert heap.reference_count(heap.module_root) == 1
    assert heap.frame_roots() == {}


def test_frame_roots_count_in_the_reference_count_while_frames_hold_them() -> None:
    heap = new_heap()
    x = heap.allocate()  # its allocating frame holds it

    heap.take_frame_root(x)
    heap.take_frame_root(x)
    heap.let_go_frame_root(x)

    assert heap.reference_count(x) == 2
    assert heap.frame_roots() == {x: 2}


def test_the_heap_refuses_to_let_go_of_a_frame_root_an_object_lacks() -> None:
    heap = new_heap()
    x, y = heap.allocate(), heap.allocate()
    heap.link(y, x)
    heap.let_go_frame_root(x)

    with pytest.raises(ValueError, match="frame root"):
        heap.let_go_frame_root(x)

    assert heap.reference_count(x) == 1


def test_letting_go_of_a_chains_last_reference_frees_it_whole() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b, c = heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, c)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(c)

    heap.let_go_frame_root(a)

    assert [heap.is_freed(x) for x in (a, b, c)] == [True, True, True]
    assert list(collector.nursery) == [heap.module_root]


def test_a_dropped_cycle_stays_whole_with_what_it_holds() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b, c = heap.allocate(), heap.allocate(), heap.allocate()
    heap.link(a, b)
    heap.link(b, a)
    heap.link(b, c)
    heap.let_go_frame_root(b)
    heap.let_go_frame_root(c)

    heap.let_go_frame_root(a)

    assert [heap.is_freed(x) for x in (a, b, c)] == [False, False, False]
    assert [heap.reference_count(x) for x in (a, b, c)] == [1, 1, 1]
    assert list(collector.nursery) == [heap.module_root, a, b, c]
