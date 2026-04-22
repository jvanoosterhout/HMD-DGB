import pytest
from DGB.Tools import IOT_tools


class TestIOTTools:
    def test_is_float_valid(self):
        assert IOT_tools.is_float("3.14") is True
        assert IOT_tools.is_float("0") is True
        assert IOT_tools.is_float("-2.5") is True

    def test_is_float_invalid(self):
        assert IOT_tools.is_float("abc") is False
        assert IOT_tools.is_float("12a") is False

    def test_is_int_valid(self):
        assert IOT_tools.is_int("42") is True
        assert IOT_tools.is_int("0") is True
        assert IOT_tools.is_int("-10") is True

    def test_is_int_invalid(self):
        assert IOT_tools.is_int("3.14") is False
        assert IOT_tools.is_int("abc") is False

    def test_strtobool_true_values(self):
        assert IOT_tools.strtobool("y") == 1
        assert IOT_tools.strtobool("yes") == 1
        assert IOT_tools.strtobool("t") == 1
        assert IOT_tools.strtobool("true") == 1
        assert IOT_tools.strtobool("on") == 1
        assert IOT_tools.strtobool("1") == 1

    def test_strtobool_false_values(self):
        assert IOT_tools.strtobool("n") == 0
        assert IOT_tools.strtobool("no") == 0
        assert IOT_tools.strtobool("f") == 0
        assert IOT_tools.strtobool("false") == 0
        assert IOT_tools.strtobool("off") == 0
        assert IOT_tools.strtobool("0") == 0

    def test_strtobool_case_insensitive(self):
        assert IOT_tools.strtobool("YES") == 1
        assert IOT_tools.strtobool("FALSE") == 0

    def test_strtobool_invalid(self):
        with pytest.raises(ValueError):
            IOT_tools.strtobool("invalid")
