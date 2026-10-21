from dataclasses import dataclass, field

from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.collector import Collector, Space
from pep848_sim.heap import Heap


@dataclass
class Spaced:
    collector: Collector = field(default_factory=Collector)
    # The nursery first, then every other space, in the order the test made them.
    spaces: list[Space] = field(default_factory=list)
    # The test's own record of each space, in the order its objects entered.
    contents: list[list[int]] = field(default_factory=list)


@st.composite
def spaced_collectors(draw: st.DrawFn) -> Spaced:
    """A heap's collector after random allocations, moves and new nurseries."""
    spaced = Spaced()
    collector = spaced.collector
    heap = Heap(collector)
    spaced.spaces = [collector.nursery, Space(), Space()]
    spaced.contents = [[heap.module_root], [], []]
    objects = [heap.module_root]
    for _ in range(draw(st.integers(min_value=0, max_value=60))):
        action = draw(st.sampled_from(["allocate", "move", "new nursery"]))
        if action == "allocate":
            x = heap.allocate()
            objects.append(x)
            spaced.contents[0].append(x)
        elif action == "move":
            x = draw(st.sampled_from(objects))
            to = draw(st.integers(min_value=0, max_value=len(spaced.spaces) - 1))
            collector.move(x, spaced.spaces[to])
            for content in spaced.contents:
                if x in content:
                    content.remove(x)
            spaced.contents[to].append(x)
        else:
            collector.nursery = Space()
            spaced.spaces.insert(0, collector.nursery)
            spaced.contents.insert(0, [])
    return spaced


def test_new_objects_enter_the_collectors_nursery_after_those_already_there() -> None:
    collector = Collector()
    heap = Heap(collector)

    a, b = heap.allocate(), heap.allocate()

    assert list(collector.nursery) == [heap.module_root, a, b]


def test_a_move_takes_an_object_out_of_its_space_and_puts_it_last() -> None:
    collector = Collector()
    heap = Heap(collector)
    a, b = heap.allocate(), heap.allocate()
    visited = Space()

    collector.move(b, visited)
    collector.move(a, visited)

    assert list(collector.nursery) == [heap.module_root]
    assert list(visited) == [b, a]


def test_new_objects_enter_the_nursery_the_collector_holds_now() -> None:
    collector = Collector()
    heap = Heap(collector)
    a = heap.allocate()
    aging = collector.nursery

    collector.nursery = Space()
    b = heap.allocate()

    assert list(aging) == [heap.module_root, a]
    assert list(collector.nursery) == [b]


@given(spaced_collectors())
def test_each_object_sits_in_one_space_in_the_order_it_entered(
    spaced: Spaced,
) -> None:
    assert [list(space) for space in spaced.spaces] == spaced.contents
