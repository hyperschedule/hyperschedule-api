"""
Module containing functions for creating and applying diffs to
JSON objects.
"""

from hyperschedule.util import Unset

def compute_diff(o1, o2):
    """
    Compute a diff that, when applied to object `o1`, will give object
    `o2`. Do not modify `o1` or `o2`.
    """
    if not isinstance(o1, dict) or not isinstance(o2, dict):
        return o2
    diff = {}
    for k in o2:
        if k not in o1:
            diff[k] = o2[k]
            continue
        if o2[k] != o1[k]:
            diff[k] = compute_diff(o1[k], o2[k])
            continue
    for k in set(o1) - set(o2):
        diff[k] = "$delete"
    return diff

def apply_diff(o, d):
    """
    Apply the diff `d` to object `o`, returning a new object.
    """
    if not isinstance(o, dict) or not isinstance(d, dict):
        return d
    o = dict(o)
    for k, v in d.items():
        if d[k] == "$delete":
            try:
                o.pop(k)
            except KeyError:
                pass
            continue
        if k not in o:
            o[k] = v
            continue
        o[k] = apply_diff(o[k], d[k])
    return o

def merge_diffs(d1, d2):
    """
    Merge diffs `d1` and `d2`, returning a new diff which is
    equivalent to applying both diffs in sequence. Do not modify `d1`
    or `d2`.
    """
    if not isinstance(d1, dict) or not isinstance(d2, dict):
        return d2
    diff = {}
    for k in set([*d1, *d2]):
        if k not in d1:
            diff[k] = d2[k]
            continue
        if k not in d2:
            diff[k] = d1[k]
            continue
        diff[k] = merge_diffs(d1[k], d2[k])
    return diff

class DiffManager:
    """
    Class for managing a series of updates to a data object. The
    abstraction provided is as follows. The class holds one "current"
    data object, which you can update via the `set_current_data`
    method. At each update, you provide an age (some integer, e.g. the
    UNIX timestamp). Then, the class stores enough bookkeeping
    information that you can later ask for a diff of the data object
    from any past age to the present. However, internal pruning
    ensures only logarithmic memory usage is necessary to allow for
    computing a diff from *any* past age.

    Thread-safe for one writer (`set_current_data`) and any number of
    readers (`get_current_data`, `get_diff_to_present`).
    """

    def __init__(self, from_state=Unset):
        """
        Construct empty diff manager. The next step is to call
        `set_current_data` with initial data object.

        Alternatively, you can construct a DiffManager from the return
        value of some other DiffManager's `from_state`. After you do
        this, the original DiffManager is in an undefined state and
        may not be used anymore.
        """
        # (age, data, [(age, diff), ...])
        if from_state is Unset:
            self.state = (Unset, Unset, [])
        else:
            self.state = from_state

    def set_current_data(self, new_age, new_data):
        """
        Initialize or update data object.
        """
        current_age, current_data, diffs = self.state
        if diffs:
            # Prune old updates. We keep at least one diff in the last
            # time step, at least one in the last two, at least one in
            # the last four, and so on. This guarantees logarithmic
            # memory usage.
            diffs = list(diffs)
            long_enough_to_keep = 1
            for i in reversed(range(len(diffs))):
                old_age, old_diff = diffs[i]
                if new_age - old_age < long_enough_to_keep:
                    diffs.pop(i)
                else:
                    long_enough_to_keep *= 2
        if current_data is not Unset:
            # Push new diff and update old diffs.
            new_diff = compute_diff(current_data, new_data)
            diffs.append((current_age, {}))
            diffs = [(old_age, merge_diffs(old_diff, new_diff))
                     for (old_age, old_diff) in diffs]
        self.state = new_age, new_data, diffs

    def get_diff_to_present(self, since):
        """
        Get the diff from the given timestamp to the present. The idea is
        that if `get_current_age` returned the value you pass as
        `since`, then applying the returned diff to the corresponding
        value of `get_current_data` at that time will give you the
        *current* value of `get_current_data`. Also, `since` can be
        `Unset` to indicate that the full data structure is desired.

        Return a tuple (diff, full, current_age), where `full` is a
        boolean which (if true) indicates that the diff is not
        actually a diff, but should rather be considered the full,
        canonical data structure.

        If `set_current_data` has never been called, return
        `util.Unset` for all three elements of the tuple.
        """
        current_age, current_data, diffs = self.state
        if since is not Unset:
            if current_data is Unset:
                return Unset, Unset, Unset
            if since >= current_age:
                return {}, False, current_age
            for age, diff in reversed(diffs):
                if since >= age:
                    return diff, False, current_age
        return current_data, True, current_age

    def get_state(self):
        """
        Return the internal state of the DiffManager. This can be passed
        to the `from_state` keyword argument of the DiffManager
        constructor, and is serializable to JSON. Other than this, you
        should not introspect or modify the state.
        """
        return self.state
