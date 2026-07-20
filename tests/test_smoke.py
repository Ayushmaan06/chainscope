"""Package skeleton sanity check - fails fast if the src layout breaks."""

import src
import src.analysis
import src.data
import src.protocols
import src.utils
import src.visualization


def test_subpackages_import():
    for pkg in (src, src.data, src.analysis, src.visualization, src.protocols, src.utils):
        assert pkg is not None
