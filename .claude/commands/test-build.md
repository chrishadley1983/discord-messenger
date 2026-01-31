# Test Build Command

You are now operating as the **Test Build Agent**. Follow the comprehensive instructions in `docs/testing/test-build-agent.md`.

## Quick Reference

### Usage
```
/test-build <mode>
```

### Available Modes

| Mode | Description |
|------|-------------|
| `critical` | Build tests for CRITICAL priority gaps |
| `high` | Build tests for HIGH priority gaps |
| `feature:<n>` | Build tests for specific feature |
| `type:<type>` | Build specific test type (unit/api/e2e) |
| `all` | Build all missing tests |

### Examples
```powershell
/test-build critical        # Critical gaps first
/test-build feature:orders  # Order tests
/test-build type:api        # API tests only
```

### Prerequisites

Run `/test-plan analyze` first to generate a test manifest.

### Test Locations

- Unit: `tests/unit/{module}/{file}.test.ts`
- API: `tests/api/{resource}/{method}.test.ts`
- Integration: `tests/integration/{flow}.test.ts`
- E2E: `tests/e2e/playwright/{flow}.spec.ts`

### Fixtures

- Test data: `tests/fixtures/data/`
- Mocks: `tests/fixtures/mocks/`
- Seeders: `tests/fixtures/seeders/`
