# Tasks

- [x] Update `implementation_plan.md` with user feedback
- [x] **Web Application Consolidation**
    - [x] Merge `web_app.py` functionality into `app.py`.
    - [x] Implement Race Prediction & Explanation mode.
    - [x] Implement Recovery Rate Analysis mode.
    - [x] Add sidebar navigation.
- [x] **Relative Evaluation Implementation**
    - [x] Update LLM prompt to use existing race-level features (`_race_dev`, etc.).
    - [x] Refine LLM prompt for better tone and feature decoding (User Feedback).
    - [x] Structure explanation to cover General Factors first, then Relative Evaluation.
- [x] **Environment Setup**
    - [x] Install `chromadb`, `python-dotenv`, `google-generativeai`.
    - [x] Create `.env` and set `GOOGLE_API_KEY`.
    - [x] Fix `NameError` and `IndentationError` in `app.py`.
    - [x] Resolve `no such table: payouts` by running `m05_update_results.py`.py` JSON output contains necessary feature
- [x] **Enhance Result Update Workflow**
    - [x] Add "Update Race Results" button to `app.py`.
    - [x] Execute `m05_update_results.py` via subprocess from the UI.
- [x] **UI Overhaul: Netkeiba-style Race Selection**
    - [x] Group race schedule by venue.
    - [x] Create a grid layout (columns for venues).
    - [x] Use buttons for race selection (Race No, Name, Time).
    - [x] Manage selection state to toggle between "List View" and "Detail View".
    - [x] Disable auto-fetch on startup (require "Get Schedule" button).
- [x] **Advanced Recovery Rate Analysis**
    - [x] Investigate if "Race Class" data exists in DB.
    - [x] Implement "Betting Strategy" selector (Box, Top N).
    - [x] Implement "Race Filter" (Race No, Class/Time).
    - [x] Implement complex payout calculation logic.
- [x] 精度可視化ダッシュボードの実装 (Phase 1) <!-- id: 4 -->
    - [x] `analytics.py` モジュールの作成 (月別・会場別・期待値分析) <!-- id: 5 -->
    - [x] `app.py` の修復と `analytics` モジュールの統合 <!-- id: 6 -->
    - [x] 動作確認とデバッグ <!-- id: 7 -->
- [x] Delete `web_app.py`
- [x] Verify the new application
- [x] **Chatbot Integration**
    - [x] Merge chatbot logic from `feature/normalization-and-chatbot` into `app.py`.
    - [x] Verify chatbot UI appearance.

- [x] **Bug Fixes (2025-12-07)**:
    - [x] Fixed `NameError` in `app.py` (Indentation).
    - [x] Fixed `KeyError: 'B'` in `config.py` (Model Aliases).
    - [x] Fixed `[FATAL] Model not loaded` (Path/Version Config).

- [x] **Future Roadmap Planning**:
    - [x] **Strategy Definition**:
        - [x] Define strategy for handling missing values in Overseas/Local race data.
        - [x] Define semantic versioning scheme for models (e.g., `v01_...`).
    - [x] **Code Modification Plan**:
        - [x] Plan updates to `m02_build_training_data.py` to include `data/kaigai` CSVs.
        - [x] Plan updates to `config.py` for versioning support.
    - [x] **Documentation**:
        - [x] Summarize the plan in the chat for user approval.

- [x] **Data Collection Optimization (Scraper)**:
    - [x] Implement `scrape_status.json` for tracking scrape timestamps.
    - [x] Implement incremental saving (CSV & JSON) in `extract_local_overseas.py`.
    - [x] Add `--resume` option (skip horses scraped < 24h ago).
    - [x] Ensure idempotent updates (overwrite existing horse records on re-scrape).
    - [/] **Scrape JRA Odds for 2024-02-10 Tokyo 11R**

- [x] **Model Training (m03) Update**:
- [x] Rename feature list file from `used_features_...` to `features_...` in `m03_train_model.py`.

- [x] **Feature Engineering Debugging & Cleanup**:
    - [x] Investigate/Fix NaN values for `騎手勝率` related features.
    - [x] Investigate/Fix NaN values for `体重増減カテゴリ`.
    - [x] Remove `開催バイアス` related feature generation.
    - [x] Drop unwanted columns: `頭数` (dup), `枠番`, `ペース`, `厩舎`.

- [x] **Prediction Metrics Analysis & Visualization**:
    - [x] Create analysis script/page to calculate:
        - Metrics: Average Win Prob, Top Prob Gap, Top Prob.
        - Outcomes: Recovery Rate, Hit Rate.
    - [x] Visualize relationships (High/Low metrics vs Outcomes).

