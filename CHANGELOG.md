# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0a3] - 2026-08-28

### Added

- Added `text`, `number`, and `select` Home Assistant entity support.
- Added configurable system sensor update rates.
- Added separate soft and hard restart controls for system devices.
- Added startup-state configuration with preset values and retained-state overrides.
- Added the `StartupPolicy` and `StartupStateInitializer` configuration interfaces.
- Added a dedicated MQTT startup-policy example and an installation helper.
- Added GitHub issue templates for bug reports and feature requests.

### Changed

- Reworked device, pin, and binding configuration around a unified context object registry.
- Standardized state-setting actions and startup-state arguments as `args: [{"state_name": ..., "state": ...}]`.
- Reworked retained-state publishing and startup application so retained state can override configured presets.
- Made configuration application lifecycle-aware, including ordered processing and gated binding dispatch while configuration is applied.
- Updated MQTT availability reporting to align with Home Assistant device discovery timing.
- Clarified documentation, installation, architecture, BCM GPIO terminology, and Binder action arguments.

### Fixed

- Prevented duplicate device, pin, and Durable Rules binding registrations.
- Fixed unique IDs for system and node devices with different configured names.
- Fixed `availability_topic` configuration for system and user-defined devices.
- Handled invalid JSON configuration with an exception and logging instead of an unhandled failure.
- Fixed action resolution after the `get_object` API change.
- Fixed `PinOut` behavior and refreshed MQTT examples.
- Corrected obsolete dependency references in the package and examples.

### Removed

- Removed the legacy `PinAPI` module and its examples.
- Replaced the `ActionArguments` module with `SetStateResolver`; consumers should use the new name.
