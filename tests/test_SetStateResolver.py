import pytest

from DGB.SetStateResolver import ArgDefinition, SetStateResolver

# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


class DummyFunction:
    """Stub function class for type hint extraction"""

    def __init__(self):
        pass


class DummyContext:
    """Simple object-style context to mimic durable c.<field> access."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def func_with_types(value: int, flag: bool, ratio: float) -> None:
    pass


def func_with_optional(value: int | None) -> None:
    pass


def func_with_union(value: int | str | None) -> None:
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def builder():
    return SetStateResolver()


# ---------------------------------------------------------------------------
# Level 1: Simple parsing and coercion
# ---------------------------------------------------------------------------


def test_parse_literal_argument(builder):
    """Test parsing literal arguments"""
    args_config = [{"count": 5}]
    defs = builder.parse_argument_definitions(args_config, func_with_types)

    assert len(defs) == 1
    assert defs[0].name == "count"
    assert defs[0].value == 5
    assert defs[0].is_context_ref is False


def test_parse_context_reference_argument(builder):
    """Test parsing context reference arguments"""
    args_config = [{"payload": "$m.payload"}]
    defs = builder.parse_argument_definitions(args_config, func_with_types)

    assert len(defs) == 1
    assert defs[0].name == "payload"
    assert defs[0].is_context_ref is True
    assert defs[0].context_path == "m.payload"


def test_coerce_string_to_bool_true(builder):
    """Test coercing string representations to bool"""
    assert builder.coerce_value("true", (bool,)) is True
    assert builder.coerce_value("1", (bool,)) is True
    assert builder.coerce_value("yes", (bool,)) is True
    assert builder.coerce_value("on", (bool,)) is True


def test_coerce_string_to_bool_false(builder):
    """Test coercing false string representations to bool"""
    assert builder.coerce_value("false", (bool,)) is False
    assert builder.coerce_value("0", (bool,)) is False
    assert builder.coerce_value("no", (bool,)) is False
    assert builder.coerce_value("off", (bool,)) is False


def test_coerce_string_to_bool_case_insensitive(builder):
    """Test bool coercion is case-insensitive"""
    assert builder.coerce_value("TRUE", (bool,)) is True
    assert builder.coerce_value("FALSE", (bool,)) is False
    assert builder.coerce_value("Yes", (bool,)) is True


def test_coerce_string_to_int(builder):
    """Test coercing string to int"""
    assert builder.coerce_value("42", (int,)) == 42
    assert builder.coerce_value("-10", (int,)) == -10
    assert builder.coerce_value("0", (int,)) == 0


def test_coerce_string_to_float(builder):
    """Test coercing string to float"""
    assert builder.coerce_value("3.14", (float,)) == 3.14
    assert builder.coerce_value("-2.5", (float,)) == -2.5
    assert builder.coerce_value("0", (float,)) == 0.0


def test_coerce_string_to_string(builder):
    """Test string to string coercion (identity)"""
    assert builder.coerce_value("hello", (str,)) == "hello"


def test_coerce_int_to_bool(builder):
    """Test coercing int to bool"""
    assert builder.coerce_value(1, (bool,)) is True
    assert builder.coerce_value(0, (bool,)) is False


def test_coerce_already_correct_type(builder):
    """Test value already has correct type returns unchanged"""
    assert builder.coerce_value(42, (int,)) == 42
    assert builder.coerce_value(True, (bool,)) is True


def test_coerce_none_returns_none(builder):
    """Test None value returns None regardless of target type"""
    assert builder.coerce_value(None, (int,)) is None
    assert builder.coerce_value(None, (bool,)) is None


def test_coerce_no_target_types_returns_unchanged(builder):
    """Test without target types returns value unchanged"""
    assert builder.coerce_value(42) == 42
    assert builder.coerce_value("hello") == "hello"


def test_resolve_context_value_dict_access(builder):
    """Test resolving value from dict context"""
    context = {"m": {"payload": "hello"}}
    value = builder.resolve_context_value("m.payload", context)
    assert value == "hello"


def test_resolve_context_value_nested_dict(builder):
    """Test resolving nested dict paths"""
    context = {"first": {"second": {"value": 42}}}
    value = builder.resolve_context_value("first.second.value", context)
    assert value == 42


def test_resolve_context_value_single_key(builder):
    """Test resolving single key"""
    context = {"payload": "test"}
    value = builder.resolve_context_value("payload", context)
    assert value == "test"


def test_resolve_context_value_list_defaults_to_last_event(builder):
    """When context value is a list, non-index access uses the last item."""
    context = {"m": [{"payload": 1}, {"payload": 100}]}
    value = builder.resolve_context_value("m.payload", context)
    assert value == 100


def test_resolve_context_value_list_with_explicit_index(builder):
    """List paths may use explicit numeric indices."""
    context = {"m": [{"payload": 1}, {"payload": 100}]}
    value = builder.resolve_context_value("m.0.payload", context)
    assert value == 1


def test_resolve_context_value_durable_object_context_list(builder):
    """Durable-style c.m list resolves non-index paths against last event."""
    context = DummyContext(m=[{"payload": 1}, {"payload": 100}])
    value = builder.resolve_context_value("m.payload", context)
    assert value == 100


def test_resolve_context_value_uses_object_attributes(builder):
    """Context paths can use attribute access for object-style contexts."""
    context = DummyContext(device=DummyContext(name="sensor"))
    value = builder.resolve_context_value("device.name", context)
    assert value == "sensor"


def test_resolve_context_value_supports_tuple_index_access(builder):
    """Tuple contexts support the same explicit index access as lists."""
    context = {"events": ({"value": 1}, {"value": 2})}
    value = builder.resolve_context_value("events.1.value", context)
    assert value == 2


def test_resolve_context_value_empty_sequence_returns_none(builder):
    """An empty list or tuple cannot provide a context value."""
    assert builder.resolve_context_value("events.value", {"events": []}) is None
    assert builder.resolve_context_value("events.value", {"events": ()}) is None


def test_resolve_context_value_out_of_range_index_returns_none(builder):
    """An explicit sequence index outside the available events returns None."""
    context = {"events": [{"value": 1}]}
    assert builder.resolve_context_value("events.1.value", context) is None


def test_extract_non_none_type_simple_type(builder):
    """Test extracting type from simple annotation"""
    target_types, accepts_none = builder._extract_non_none_types(int)
    assert target_types == (int,)
    assert accepts_none is False


def test_extract_non_none_type_optional(builder):
    """Test extracting type from Optional annotation"""
    target_types, accepts_none = builder._extract_non_none_types(str | None)
    assert target_types == (str,)
    assert accepts_none is True


def test_extract_non_none_type_union_with_none(builder):
    """Test extracting type from Union with None"""
    target_types, accepts_none = builder._extract_non_none_types(int | None)
    assert target_types == (int,)
    assert accepts_none is True


def test_extract_non_none_type_union_no_none(builder):
    """Test extracting type from Union without None"""
    target_types, accepts_none = builder._extract_non_none_types(int | str)
    assert target_types == (int, str)
    assert accepts_none is False


def test_coerce_value_prefers_existing_union_type_match(builder):
    """Int input should stay int when union includes int, even if bytes is first."""
    result = builder.coerce_value(42, (bytes, str, int, float))
    assert result == 42
    assert isinstance(result, int)


def test_coerce_value_union_falls_back_to_first_type(builder):
    """When no union type matches, fallback to the first candidate type."""
    result = builder.coerce_value("42", (bytes, int))
    assert result == b"42"


def test_coerce_value_union_uses_strict_type_match(builder):
    """Do not accept subclass matches when checking union candidates."""
    result = builder.coerce_value(True, (int,))
    assert result == 1
    assert type(result) is int


def test_parse_argument_definitions_stores_all_union_target_types(builder):
    """Union annotations are preserved for smarter type matching."""

    def func(value: bytes | str | float) -> None:
        pass

    defs = builder.parse_argument_definitions([{"value": 5}], func)

    assert defs[0].target_types == (bytes, str, float)


def test_build_call_args_with_literals(builder):
    """Test building call args with literal values"""
    arg_defs = [
        ArgDefinition(
            name="value",
            value=42,
            is_context_ref=False,
            target_types=(int,),
        ),
        ArgDefinition(
            name="flag",
            value="true",
            is_context_ref=False,
            target_types=(bool,),
        ),
    ]

    context = {}
    call_args = builder.build_call_args(arg_defs, context)

    assert call_args["value"] == 42
    assert call_args["flag"] is True


def test_build_call_args_with_context_refs(builder):
    """Test building call args with context references"""
    arg_defs = [
        ArgDefinition(
            name="payload",
            value="$m.payload",
            is_context_ref=True,
            context_path="m.payload",
            target_types=(str,),
        ),
    ]

    context = {"m": {"payload": "hello"}}
    call_args = builder.build_call_args(arg_defs, context)

    assert call_args["payload"] == "hello"


# ---------------------------------------------------------------------------
# Level 2: Error semantics
# ---------------------------------------------------------------------------


def test_parse_argument_multiple_keys_parses_all_entries(builder):
    """A single dict may define multiple arguments."""
    args_config = [{"a": 1, "b": 2}]
    defs = builder.parse_argument_definitions(args_config, func_with_types)
    assert [d.name for d in defs] == ["a", "b"]
    assert [d.value for d in defs] == [1, 2]


def test_parse_argument_empty_dict_raises_value_error(builder):
    """Test parsing an empty arg dict raises ValueError"""
    args_config = [{}]
    with pytest.raises(ValueError, match="at least one"):
        builder.parse_argument_definitions(args_config, func_with_types)


def test_parse_argument_non_dict_config_raises_type_error(builder):
    """Each argument configuration entry must be a dictionary."""
    with pytest.raises(TypeError, match="must be a dict"):
        builder.parse_argument_definitions(["invalid"], func_with_types)


def test_parse_argument_empty_name_raises_value_error(builder):
    """Test parsing argument with empty key raises ValueError"""
    args_config = [{"": 5}]
    with pytest.raises(ValueError, match="empty key"):
        builder.parse_argument_definitions(args_config, func_with_types)


def test_coerce_invalid_string_to_float_raises_value_error(builder):
    """Invalid float input raises ValueError."""
    with pytest.raises(ValueError, match="Could not coerce"):
        builder.coerce_value("not_a_number", (float,))


def test_coerce_invalid_string_to_bool_raises_value_error(builder):
    """Invalid bool input raises ValueError."""
    with pytest.raises(ValueError, match="Could not coerce"):
        builder.coerce_value("invalid_bool", (bool,))


def test_coerce_invalid_value_to_float_raises_value_error(builder):
    """Values rejected by float conversion raise ValueError."""
    with pytest.raises(ValueError, match="Could not coerce"):
        builder.coerce_value(object(), (float,))


def test_coerce_invalid_value_to_custom_type_raises_value_error(builder):
    """Values rejected by custom conversion raise ValueError."""

    class CustomType:
        def __init__(self, value):
            raise TypeError(f"unsupported value: {value!r}")

    with pytest.raises(ValueError, match="Could not coerce"):
        builder.coerce_value("invalid", (CustomType,))


def test_resolve_context_path_missing_key_returns_none(builder):
    """Test resolving missing key returns None"""
    context = {"m": {"other": "value"}}
    value = builder.resolve_context_value("m.payload", context)
    assert value is None


def test_resolve_context_path_stops_at_none(builder):
    """Test context path resolution stops when encountering None"""
    context = {"m": None}
    value = builder.resolve_context_value("m.payload", context)
    assert value is None


def test_resolve_context_path_empty_dict(builder):
    """Test resolving from empty dict returns None"""
    context = {}
    value = builder.resolve_context_value("m.payload", context)
    assert value is None


def test_parse_empty_args_config_returns_empty_list(builder):
    """Test parsing empty config returns empty list"""
    defs = builder.parse_argument_definitions(None, func_with_types)
    assert defs == []

    defs = builder.parse_argument_definitions([], func_with_types)
    assert defs == []
