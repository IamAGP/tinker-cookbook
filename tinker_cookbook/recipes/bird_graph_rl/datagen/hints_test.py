from .hints import hint
from .structures import enumerate_structures


def test_hints_are_deterministic_and_not_questions():
    s=enumerate_structures()[0]
    a=[hint(s,f'i_{i}') for i in range(1000)]
    assert a==[hint(s,f'i_{i}') for i in range(1000)]
    assert .89 <= sum(x is not None for x in a)/len(a) <= .95
    assert all('refers to' in x for x in a if x)
