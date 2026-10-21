from collections import Counter

from hypothesis import given
from hypothesis import strategies as st

from pep848_sim.heap import Heap


@st.composite
def linked_heaps(draw: st.DrawFn) -> tuple[Heap, list[int]]:
    """A heap built by random allocations and links, and the objects in it."""
    heap = Heap()
    objects = [heap.allocate()]
    for _ in range(draw(st.integers(min_value=0, max_value=60))):
        if draw(st.booleans()):
            objects.append(heap.allocate())
        else:
            heap.link(draw(st.sampled_from(objects)), draw(st.sampled_from(objects)))
    return heap, objects


def test_a_new_object_holds_no_references_and_has_none_into_it() -> None:
    heap = Heap()

    x = heap.allocate()

    assert heap.references(x) == ()
    assert heap.reference_count(x) == 0


def test_each_allocation_is_a_different_object() -> None:
    heap = Heap()

    assert heap.allocate() != heap.allocate()


def test_each_link_raises_the_count_of_its_target_a_repeat_included() -> None:
    heap = Heap()
    x, y = heap.allocate(), heap.allocate()

    heap.link(x, y)
    heap.link(x, y)

    assert heap.reference_count(y) == 2


def test_an_object_lists_its_references_in_the_order_they_were_made() -> None:
    heap = Heap()
    a, b, c = heap.allocate(), heap.allocate(), heap.allocate()

    heap.link(a, c)
    heap.link(a, b)
    heap.link(a, c)

    assert heap.references(a) == (c, b, c)


@given(linked_heaps())
def test_an_objects_count_is_how_often_the_heap_references_it(
    built: tuple[Heap, list[int]],
) -> None:
    heap, objects = built
    held = Counter(target for x in objects for target in heap.references(x))

    assert {x: heap.reference_count(x) for x in objects} == {
        x: held[x] for x in objects
    }
