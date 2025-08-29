# Elon System Flow Map

```mermaid
flowchart LR
    subgraph Edit Inputs
        Cfg[runs/rpl_example.yaml\nEdit claim, model, K, R, T]
        Prompts[heretix/prompts/rpl_g5_v2.yaml\nModify paraphrases / templates]
    end

    subgraph Operate
        Run["uv run heretix run --config runs/rpl_example.yaml --out runs/smoke.json"]
        DB[(runs/heretix.sqlite)]
        OutFile[runs/smoke.json]
    end

    subgraph Review Outputs
        Inspect[Inspect JSON, CI width, stability\nCheck DB tables runs, samples]
    end

    Cfg --> Run
    Prompts --> Run
    Run --> DB
    Run --> OutFile
    DB --> Inspect
    OutFile --> Inspect
    Inspect --> Cfg
    Inspect --> Prompts
```

## Iteration Tips
- **Tighten confidence intervals:** Increase `K`, `R`, or `T` in `runs/rpl_example.yaml`.
- **Improve paraphrase balance:** Adjust templates in `heretix/prompts/rpl_g5_v2.yaml`.
- **Reuse cached samples:** Leave `runs/heretix.sqlite` intact between runs.
- **Track changes:** Commit edited config/prompt files alongside output JSON for auditability.

Example loop:
1. Edit `runs/rpl_example.yaml` to tweak `K` and `R`.
2. Run `uv run heretix run --config runs/rpl_example.yaml --mock --out runs/smoke.json`.
3. Review `runs/smoke.json` and `runs/heretix.sqlite`.
4. Repeat until CI width and stability meet targets.
