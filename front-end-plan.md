# Front-End Plan for Heretix Terminal UI

## Design Vision
Create a minimal, retro-terminal aesthetic UI for Heretix RPL analysis using only Python stdlib and pure HTML/CSS.

## Core Principles (Elon's Delete-First Approach)
- **No dependencies**: stdlib only (no Flask, no npm, no React)
- **No build process**: Pure HTML with inline styles
- **Minimal files**: 3 files total (~250 lines)
- **Easy to delete**: Isolated in `ui/` directory
- **No schema changes**: Write to separate DB

## Visual Design Requirements

### Style Guide
- **Background**: #0a0a0a (near black)
- **Primary text**: #00ff41 (terminal green)
- **Font**: 'Courier New', monospace
- **Effects**: Subtle glow with text-shadow
- **Layout**: Centered, max-width 800px

### Screen 1: Input Form
- Large "HERETIX" title with glow effect
- Subtitle: "How likely is the following true?"
- Subtext: "Internal knowledge only (no retrieval)"
- Large textarea for claim entry (600 char max)
- Prompt version selector (rpl_g5_v4 default)
- Mock mode checkbox
- Collapsible advanced settings (K, R, T, B, max_tokens)
- "ANALYZE CLAIM" button

### Screen 2: Results Display
- Display claim text at top
- Giant percentage display (120px font)
- TRUE/FALSE verdict (based on p ≥ 0.5)
- Metrics line: CI95, width, stability, compliance
- "New Claim" link back to input

## Technical Architecture

### File Structure
```
ui/
├── index.html      # Input screen (~100 lines)
├── results.html    # Results screen (~80 lines)
└── serve.py        # HTTP server (~100 lines)
```

### Server Implementation (serve.py)
```python
# Using stdlib http.server
- GET /: Serve index.html
- POST /run: Process claim analysis
  1. Parse form data
  2. Validate inputs (claim ≤ 600 chars)
  3. Build temp config JSON
  4. Set environment:
     - HERETIX_DB_PATH=runs/heretix_ui.sqlite
     - HERETIX_RPL_SEED=42
  5. Execute: uv run heretix run --config <tmp> --out <tmp.json>
  6. Parse results JSON
  7. Replace placeholders in results.html
  8. Return rendered HTML
```

### Form Fields
| Field | Type | Default | Required |
|-------|------|---------|----------|
| claim | textarea | - | Yes |
| prompt_version | select | rpl_g5_v4 | Yes |
| mock | checkbox | false | No |
| K | number | 16 | No (advanced) |
| R | number | 2 | No (advanced) |
| T | number | 8 | No (advanced) |
| B | number | 5000 | No (advanced) |
| max_output_tokens | number | 1024 | No (advanced) |

### Database Strategy
- UI runs write to: `runs/heretix_ui.sqlite`
- Mock runs write to: `runs/heretix_mock.sqlite`
- Main DB untouched: `runs/heretix.sqlite`

## Safety Guarantees

1. **Repository Protection**
   - All work in `front-end` branch
   - New `ui/` directory only
   - No modifications to existing code
   - No new .gitignore entries needed

2. **Execution Safety**
   - Subprocess with args list (no shell injection)
   - Input validation and length limits
   - 600-second timeout protection
   - Temp file cleanup in finally blocks

3. **Dependency Safety**
   - Zero new dependencies
   - Uses only Python stdlib
   - No package.json or node_modules
   - No build artifacts

## Implementation Steps

1. **Create UI directory**
   ```bash
   mkdir ui
   ```

2. **Create index.html**
   - Terminal aesthetic styling
   - Form with claim input
   - Advanced settings in <details> tag

3. **Create results.html**
   - Template with {PLACEHOLDERS}
   - Giant percentage display
   - Metrics line

4. **Create serve.py**
   - HTTPServer and BaseHTTPRequestHandler
   - Form parsing with urllib.parse
   - Subprocess execution
   - Simple string replacement for templating

5. **Test**
   ```bash
   python ui/serve.py
   # Open http://localhost:5000
   ```

## Testing Checklist

- [ ] Mock mode works without API key
- [ ] Live mode calls real RPL analysis
- [ ] Claims are validated (length, required)
- [ ] Advanced settings apply correctly
- [ ] Results display matches RPL output
- [ ] Temp files are cleaned up
- [ ] Timeout protection works
- [ ] Error pages display nicely

## Rollback Plan

If the UI experiment fails or isn't needed:
```bash
rm -rf ui/
git checkout -- .
```

The entire feature can be removed without any trace or impact on the core repository.

## Success Metrics

- **Lines of code**: < 300 total
- **Dependencies added**: 0
- **Build time**: 0 (no build)
- **Time to implement**: < 1 hour
- **Time to delete**: < 1 second

## Notes

- RPL is prior-only, no retrieval options shown
- Using operating defaults for K/R/T/B
- Deterministic seed (42) for reproducible results
- No JavaScript needed for MVP
- Can add minimal JS later if needed (form validation, loading states)