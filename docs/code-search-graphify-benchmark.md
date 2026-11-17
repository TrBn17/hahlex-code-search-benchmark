# Phase 3: Graphify vs CodeGraph vs ripgrep — AI Agent Benchmark trên Dự án LMS (`hahlex-edu`)

**Ngày thực nghiệm:** 2026-11-17  
**Mục tiêu:** Đánh giá xem **Graphify** (`Graphify-Labs/graphify`) có thực sự mang lại lợi ích so với `ripgrep`, `CodeGraph` và `Adaptive Search` khi AI Coding Agent giải quyết các task LMS thực tế hay không.

---

## 1. Nghiên cứu và Cài đặt Graphify

### 1.1. Phiên bản, Commit & Dependency
- **Repository:** `https://github.com/Graphify-Labs/graphify` (nhánh mặc định `v8`, commit `480b61ed91cbc08177dc2c60caa9ffd6c9b95749`, 2026-11-16)
- **Package cài đặt:** `graphifyy` phiên bản **`0.9.111`** (Apache-2.0), cài trong môi trường cô lập [`benchmarks/code-search/phase3/.venv`](../benchmarks/code-search/phase3/.venv) (không chạy `graphify install`, không sửa `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` hay cấu hình agent mặc định).
- **Dependencies chính:** `networkx 3.6.1`, `graspologic 3.4.4` + `graspologic-native 1.3.1` (Leiden community detection), `tree-sitter 0.25.2` + các grammar `tree-sitter-typescript 0.23.2`, `tree-sitter-python 0.25.0`, `tree-sitter-javascript 0.25.0`, `rapidfuzz 3.14.6`, `pyyaml 6.0.3`, `mcp 2.3.0`.
- **Chế độ chạy local-first:** Thiết lập `GRAPHIFY_BACKEND=none`, `GRAPHIFY_VIZ_NODE_LIMIT=0`, `GRAPHIFY_QUERY_LOG_DISABLE=1` — xử lý 100% cục bộ bằng Tree-sitter AST, **không** gọi LLM ngoài, **không** upload source code lên cloud.

### 1.2. Kiến trúc Graphify & Khác biệt Kỹ thuật với CodeGraph

| Tiêu chí kỹ thuật | CodeGraph (`1.6.2`) | Graphify (`0.9.111`, local AST mode) |
|---|---|---|
| **Engine parse** | Native Rust kernel + Tree-sitter | Python multiprocessing (`20` workers) + `tree-sitter` |
| **Lưu trữ** | SQLite (`.codegraph/codegraph.db`, WAL + FTS5) — **477.16 MB** | `graphify-out/graph.json` (NetworkX JSON) + `cache/` + `GRAPH_REPORT.md` — **206.21 MB** (`2,461` files) |
| **Indexing lần đầu (cold)** | **71.22 s** (`4,906` files, `114,773` nodes, `387,040` edges) | **154.26 s** (`6,060` files, `75,005` nodes, `236,226` edges, `1,864` communities); Peak RSS **1,786.62 MB**; CPU **293.62 s** |
| **Incremental sync (warm, 0 đổi)** | **`codegraph sync`: 843.86 ms** (chỉ sync diff) | **`graphify update .`: 112.33 s**, Peak RSS **2,568.36 MB** (vẫn chạy lại phân cụm Leiden & ghi report) |
| **Độ trễ 1 lệnh query CLI** | **~1.21 s** (`430.09 MB` Peak RSS) | **~4.58 s** (`297.33 MB` Peak RSS — nạp `graph.json` 75k nodes vào NetworkX mỗi lần chạy) |
| **Loại cạnh & độ tin cậy** | Nodes/edges AST + framework routes (`1,011` routes NestJS/FastAPI), dynamic dispatch | Gắn nhãn **`EXTRACTED`** (`220,344` cạnh) và **`INFERRED`** (`15,882` cạnh), hỗ trợ thêm **tài liệu Markdown / rationale (`6,868` cạnh `rationale_for`)** |
| **Truy vấn chính** | `explore`, `query`, `callers`, `callees`, `impact`, `node` | `query` (BFS/DFS có `--budget` token), `path` (shortest path), `explain`, `affected`, `god-nodes` |

---

## 2. Đánh giá Chất lượng Graph của Graphify trên `hahlex-edu`

Kiểm chứng trực tiếp trên `graphify-out/graph.json`:
- **Tổng quy mô:** `75,005` nodes, `236,226` edges (`220,344` `EXTRACTED`, `15,882` `INFERRED`), `1,864` communities.
  - Phân bố cạnh chính: `calls` (`62,180`), `contains` (`54,084`), `imports` (`45,858`), `imports_from` (`29,345`), `references` (`22,867`), `rationale_for` (`6,868`), `uses` (`5,507`), `method` (`4,801`), `indirect_call` (`2,848`), `inherits` (`912`).
- **Cảnh báo trích xuất:** `134` file `.sql` bị bỏ qua do thiếu `tree_sitter_sql`; `331` file (`1.18 MB`, gồm `.ps1`, `pyproject.toml`, một số file khai báo như `ai_engine/db/models.py`) không sinh node; `1` file test (`class-opening.e2e-spec.ts:434`) lỗi parse một phần.
- **Khả năng truy vết ranh giới TS ↔ Python & HTTP:**
  - `graphify path "ServicePrincipalGuard" "verify_service_token"` (có hướng) trả về **`No directed path found`**.
  - Khi chạy `--undirected`, Graphify tìm được đường đi 5 hop giữa TS và Python (`AiPlatformClient` ↔ `HttpAiPlatformClient` ↔ **`4.3 Cross-service: how education learns a centre's features`** [Markdown doc, `INFERRED 0.95`] ↔ `require_education_service()` ↔ `credits_router.py`).
  - **Nhận xét quan trọng:** Graphify **không** nối được HTTP endpoint xuyên ngôn ngữ từ code thuần; nó chỉ bắc cầu được TS ↔ Python gián tiếp khi có **tài liệu Markdown** nhắc tới cả hai symbol (qua cạnh `INFERRED` từ doc-to-code). Nếu không có doc node hoặc chạy truy vấn có hướng, ranh giới HTTP vẫn bị đứt như CodeGraph.
- **Độ tươi của graph:** Vì `graphify update .` (warm) mất **112.33 s** và **2.57 GB RAM**, độ tươi thực tế khi code liên tục kém xa `codegraph sync` (**0.84 s**).

---

## 3. Thiết kế Benchmark & Phạm vi Thực thi

- **Tái sử dụng Task & Ground Truth:** Giữ nguyên **5 task LMS (T1–T5)** và tập `ground_truth_files` / `critical_files` từ [`benchmarks/code-search/tasks.json`](../benchmarks/code-search/tasks.json).
- **6 Phương pháp so sánh:**
  - **A (Baseline):** `git grep` + `read_file` (cấm `rg`, `codegraph`, `graphify`).
  - **B (`ripgrep`):** `rg` + `read_file` (cấm `codegraph`, `graphify`).
  - **C (`CodeGraph`):** `codegraph` CLI + `read_file` khi cần (cấm `rg`, `git grep`, `graphify`).
  - **D (`Adaptive v1`):** `rg` + `codegraph` theo cây quyết định Phase 2 (cấm `graphify`).
  - **E (`Graphify-only`):** `graphify` CLI (`query`, `path`, `explain`, `affected`, `god-nodes`) + `read_file` xác minh (cấm `rg`, `git grep`, `codegraph`).
  - **F (`Adaptive v2`):** Agent tự chọn giữa `rg`, `codegraph`, và `graphify` tùy nhu cầu, không gọi cả ba mặc định.
- **Số phiên thực chạy & Giới hạn trung thực:**
  - Đã khởi chạy **30 phiên AI Agent độc lập** (`5 tasks × 6 arms × 1 repetition`, model `flash`, thứ tự arm **được randomize** cho từng task: T1 `[E,B,F,A,C,D]`, T2 `[C,F,A,E,D,B]`, T3 `[F,D,E,B,A,C]`, T4 `[B,E,A,C,F,D]`, T5 `[D,A,C,F,B,E]`).
  - **Không chạy đủ 90 phiên (3 repetitions)** do giới hạn thời gian thực thi phiên (~2.5–3.5 phút/wave song song); giữ đúng nguyên tắc **không lấy 20 phiên Phase 2 gộp vào Phase 3**.
  - Lưu ý 2 lỗi dừng thật của agent trong 30 phiên: `T4 Baseline` và `T5 Adaptive v2` rơi vào trạng thái `waiting_for_dependents` (không gửi báo cáo cuối), nên bị tính `Recall = 0.00`, `Task Success = False`.

---

## 4. Kết quả Benchmark Tổng hợp (30 phiên AI Agent độc lập)

### 4.1. Bảng so sánh bắt buộc (Mean / Median / P95)

| Metric | Baseline (A) | ripgrep (B) | CodeGraph (C) | Adaptive v1 (D) | Graphify (E) | Adaptive v2 (F) |
|---|---|---|---|---|---|---|
| **Context time (Mean / Median / P95)** | 17.2s / 18.0s / 30.0s | 34.4s / 25.0s / 59.0s | 33.8s / 12.0s / 105.0s | **12.8s / 5.0s / 40.0s** | 72.0s / 49.0s / 137.0s | 46.2s / 42.0s / 101.0s |
| **Completion time (Mean / Median / P95)** | **53.4s / 43.0s** / 96.0s | 58.2s / 46.0s / **88.0s** | 103.8s / 89.0s / 210.0s | 123.6s / 112.0s / 202.0s | 146.2s / 137.0s / 228.0s | 114.0s / 101.0s / 202.0s |
| **Input tokens (Mean / Median)** | **76,366 / 70,156** | 77,417 / 75,226 | 83,993 / **56,834** | 92,497 / 88,032 | 82,548 / 73,323 | 125,682 / 74,360 |
| **Cache read tokens (Mean)** | **255,060** | 271,096 | 491,733 | 648,719 | 505,580 | 678,584 |
| **Output tokens (Mean)** | **7,856** | 9,806 | 11,452 | 10,972 | 15,639 | 9,826 |
| **Tool calls (Mean / Median)** | 16.0 / 17 | **15.6** / 18 | 18.8 / 22 | 26.2 / 29 | 21.0 / **16** | 27.2 / 19 |
| **Duplicate `read_file` (Total / 5 runs)** | **8** | 10 | 9 | 14 | 14 | 19 |
| **Recall / F1 (Mean)** | 0.7333 / 0.4357 | 0.9167 / 0.6128 | 0.8667 / 0.5468 | **0.9833 / 0.6263** | 0.7914 / 0.5908 | 0.7667 / 0.4507 |
| **Missed GT files (Total / 43)** | 15 | 3 | 5 | **1** | 8 | 13 |
| **Task success rate** | 60% (3/5) | 80% (4/5) | 80% (4/5) | **100% (5/5)** | 60% (3/5) | 80% (4/5) |
| **Peak RAM (CLI query / index)** | 45.2 MB / 0 MB | **9.0 MB / 0 MB** | 430.1 MB / N/A | 428.5 MB / N/A | 297.3 MB / **1,786.6 MB** | 430.1 MB / 1,786.6 MB |
| **Indexing overhead (Cold / Warm)** | **0s / 0 MB** | **0s / 0 MB** | 71.22s / 0.84s (477.2 MB) | 71.22s / 0.84s (477.2 MB) | 154.26s / 112.33s (206.2 MB) | ~225s / ~113s (683.4 MB) |

*(Ghi chú: Bảng giá API theo tài khoản Antigravity nội bộ không công khai chi tiết USD cho model `flash`, nên API cost bằng tiền ghi nhận là `N/A`; chi phí được đo trực tiếp qua `Input tokens`, `Cache read tokens` và `Output tokens`.)*

---

## 5. Phân tích Chuyên sâu Theo Từng Task (T1 – T5)

| Task | Arm | Ctx Time | E2E Time | Tools (S/R) | Input Tok | Cache Tok | Output Tok | Recall | F1 | Success |
|---|---|---|---|---|---|---|---|---|---|---|
| **T1** (Narrow Symbol) | Baseline | 24.0s | 52.0s | 17 (5/12) | 60,525 | 284,024 | 6,481 | 1.00 | 0.62 | Pass |
| | ripgrep | 58.0s | 75.0s | 19 (3/16) | 75,226 | 383,949 | 8,168 | 1.00 | 0.53 | Pass |
| | CodeGraph | 105.0s | 122.0s | **12** (12/0) | **55,587** | **174,499** | 8,457 | 1.00 | **0.67** | Pass |
| | Adaptive v1 | **5.0s** | **49.0s** | 15 (2/13) | 64,280 | 184,943 | **5,853** | 1.00 | 0.62 | Pass |
| | Graphify | 137.0s | 137.0s | 16 (8/8) | 58,304 | 205,792 | 8,342 | 0.60 | 0.46 | **Fail** |
| | Adaptive v2 | 55.0s | 55.0s | 18 (4/14) | 68,180 | 332,261 | 7,940 | 1.00 | 0.56 | Pass |
| **T2** (API → Service → DB) | Baseline | 30.0s | 42.0s | 22 (4/18) | 68,094 | 364,222 | 5,396 | 0.67 | 0.47 | Fail |
| | ripgrep | **25.0s** | **36.0s** | **18** (3/15) | 105,985 | **225,698** | 7,815 | 0.67 | 0.50 | Fail |
| | CodeGraph | 43.0s | 62.0s | 25 (11/14) | **56,834** | 324,577 | 5,402 | 0.50 | 0.43 | Fail |
| | Adaptive v1 | 40.0s | 65.0s | 21 (3/18) | 72,894 | 378,736 | **5,340** | **1.00** | **0.63** | **Pass** |
| | Graphify | 49.0s | 88.0s | 24 (4/20) | 75,621 | 421,404 | 7,030 | 0.83 | 0.59 | Pass |
| | Adaptive v2 | 101.0s | 101.0s | 19 (6/13) | 74,360 | 462,269 | 7,142 | 0.83 | 0.53 | Pass |
| **T3** (Multi-module Bug) | Baseline | 18.0s | **43.0s** | 12 (8/4) | **70,156** | **274,512** | 12,492 | 1.00 | 0.48 | Pass |
| | ripgrep | 59.0s | 88.0s | **11** (4/7) | 97,477 | 363,106 | **9,926** | 1.00 | 0.56 | Pass |
| | CodeGraph | **5.0s** | 210.0s | 24 (13/11) | 188,187 | 1,375,381 | 23,826 | 1.00 | 0.47 | Pass |
| | Adaptive v1 | **5.0s** | 190.0s | 36 (8/28) | 144,022 | 1,292,518 | 17,963 | 1.00 | 0.56 | Pass |
| | Graphify | 49.0s | 87.0s | **11** (4/7) | 73,323 | 346,262 | 14,216 | 0.86 | **0.71** | Pass |
| | Adaptive v2 | 42.0s | 202.0s | 51 (8/42) | 330,410 | 1,612,995 | 18,734 | 1.00 | 0.36 | Pass |
| **T4** (Blast Radius) | Baseline | 4.0s | 96.0s | 17 (14/3) | 105,196 | 110,266 | 3,872 | 0.00 | 0.00 | Fail* |
| | ripgrep | 5.0s | 46.0s | 18 (3/15) | 42,773 | 164,455 | 10,261 | 1.00 | **0.87** | Pass |
| | CodeGraph | **4.0s** | **36.0s** | **11** (10/1) | **36,002** | **98,767** | **8,684** | 1.00 | 0.68 | Pass |
| | Adaptive v1 | 5.0s | 202.0s | 29 (9/18) | 93,256 | 747,773 | 12,941 | 1.00 | 0.76 | Pass |
| | Graphify | 31.0s | 228.0s | **11** (5/6) | 66,563 | 452,415 | 26,179 | 1.00 | 0.79 | Pass |
| | Adaptive v2 | 21.0s | 69.0s | 12 (8/4) | 55,166 | 207,447 | 9,137 | 1.00 | 0.81 | Pass |
| **T5** (Cross-language) | Baseline | 10.0s | **34.0s** | **12** (7/5) | 77,858 | 242,275 | 11,041 | **1.00** | 0.60 | Pass |
| | ripgrep | 25.0s | 46.0s | **12** (5/7) | **65,626** | **218,271** | 12,862 | 0.92 | **0.61** | Pass |
| | CodeGraph | 12.0s | 89.0s | 22 (6/16) | 83,354 | 485,439 | 10,893 | 0.83 | 0.49 | Pass |
| | Adaptive v1 | **9.0s** | 112.0s | 30 (6/24) | 88,032 | 639,623 | 12,764 | 0.92 | 0.55 | Pass |
| | Graphify | 94.0s | 191.0s | 43 (8/33) | 138,928 | 1,102,025 | 22,427 | 0.67 | 0.41 | **Fail** |
| | Adaptive v2 | 12.0s | 143.0s | 36 (6/30) | 100,293 | 777,950 | 6,178 | 0.00 | 0.00 | Fail* |

### Trả lời phân tích chuyên sâu cho 5 Task
1. **T1 (Narrow Symbol Search):** **Graphify tạo overhead rất lớn và thất bại.** `Graphify` mất **137.0 s** (lâu hơn Adaptive v1 `49.0 s` tới **2.8×**) vì phải chạy 8 lệnh `graphify` CLI (~4.5s/lần) và vẫn bỏ sót `approve.ts` & `ai-messages.controller.ts` (`Recall = 0.60`, Fail). Ngược lại, `Adaptive v1` (`5s` context, `49s` E2E) và `ripgrep` (`75s` E2E) đều đạt `Recall = 1.00`.
2. **T2 (API → Service → DB):** **Adaptive v1 (`rg + CodeGraph`) chính xác và đầy đủ nhất (`Recall = 1.00`, `F1 = 0.63`).** `Graphify` (`Recall = 0.83`, `88s`) vượt trội `CodeGraph-only` (`0.50`, `62s`) và `ripgrep-only` (`0.67`, `36s`) vì `explain publishGradebook` kéo được cả `load.ts` lẫn `schema.ts`, nhưng chậm hơn `Adaptive v1` và tốn nhiều `read_file` hơn (`20` vs `18`).
3. **T3 (Multi-module Bug):** Trong Phase 3, cả `ripgrep`, `Baseline`, `CodeGraph`, `Adaptive v1`, `Adaptive v2` đều đạt `Recall = 1.00`, còn `Graphify` đạt `0.86` (bỏ sót `approve.ts`) với `F1 = 0.71` nhờ ít `read_file` hơn (`7` lần). Tuy nhiên **`Adaptive v2` bị phình token nghiêm trọng** (`330,410` input tokens, `1.61M` cache tokens, `51` tool calls) do có quá nhiều công cụ để kiểm chứng chéo.
4. **T4 (Blast Radius Analysis):** **`CodeGraph` thắng tuyệt đối về tốc độ và chi phí** (`4.0s` context, **`36.0s` E2E**, `11` tool calls, **`36,002` input tokens**, `Recall = 1.00`). `Graphify` cũng đạt `Recall = 1.00` nhưng mất tới **`228.0s` E2E** (chậm hơn CodeGraph **6.3×**) và tốn `26,179` output tokens. `ripgrep` nhanh thứ nhì (`46.0s`, `F1 = 0.87`).
5. **T5 (Cross-language / HTTP Boundary):** **Graphify thất bại (`Recall = 0.67`, `191s` E2E, `43` tool calls, `1.10M` cache tokens)** — không nối được ranh giới HTTP TS ↔ Python trong chế độ mặc định (`No directed path found`), buộc agent phải đọc tới `33` file! `Baseline` (`34s`, `Recall = 1.00`) và `ripgrep` (`46s`, `Recall = 0.92`, `F1 = 0.61`) hiệu quả vượt trội.

---

## 6. Kết luận Kỹ thuật & Chiến lược Đề xuất

### Trả lời 6 câu hỏi quyết định

1. **Graphify có tốt hơn CodeGraph không? Tốt hơn ở loại task nào?**
   - **Không tốt hơn tổng thể.** CodeGraph vượt trội Graphify về Task Success (`80%` vs `60%`), tốc độ E2E (`103.8s` vs `146.2s`), tốc độ index (`71.2s` vs `154.3s`), incremental sync (`0.84s` vs `112.3s`), và đặc biệt ở **T4 Blast Radius** (`36s` vs `228s`) và **T1** (`100%` vs `60%`).
   - Graphify chỉ nhỉnh hơn ở **T2** (`Recall = 0.83` vs `0.50` của CodeGraph-only) và khả năng bắc cầu **code ↔ Markdown docs** qua cạnh `INFERRED`.

2. **Graphify có thực sự tiết kiệm token và thời gian cho AI Agent?**
   - **Không trên codebase `hahlex-edu` (~6,000 files).** Tuyên bố "giảm 71.5x–80% token" trong README của Graphify không lặp lại được ở benchmark thực tế: Graphify-only tốn **nhiều input tokens hơn** Baseline/ripgrep (`82.5k` vs `76.4k–77.4k`), **gấp đôi** `cache_read_tokens` (`505.6k` vs `255k–271k`), **gấp đôi** `output_tokens` (`15.6k` vs `7.9k`), và **chậm hơn 2.5×** về thời gian hoàn thành (`146.2s` vs `53.4s–58.2s`).

3. **Graphify có khắc phục được những điểm yếu đã phát hiện của CodeGraph?**
   - **Không.** Graphify không giải quyết được ranh giới HTTP TS ↔ Python ở T5 (chỉ nối được gián tiếp nếu có file Markdown nhắc cả 2 symbol trong `--undirected`), trong khi lại phát sinh thêm độ trễ CLI `4.58s/lần` và chi phí update `112.3s / 2.57 GB RAM`.

4. **Có nên thay CodeGraph bằng Graphify hay giữ cả hai?**
   - **Không thay CodeGraph bằng Graphify, và không cần giữ Graphify cho tác vụ coding thông thường.** Chi phí duy trì thêm `graphify-out/` (`206 MB` + `112s` mỗi lần update) không bù đắp được lợi ích.

5. **Adaptive v2 có mang lại lợi ích đủ lớn để bù thêm độ phức tạp và tài nguyên?**
   - **Không.** `Adaptive v2` (`rg + CodeGraph + Graphify`) có `Task Success` thấp hơn `Adaptive v1` (`80%` vs `100%`), tốn nhiều input tokens nhất (`125.7k` vs `92.5k`), nhiều tool calls nhất (`27.2`), và `duplicate reads` cao nhất (`19`). Việc đưa công cụ thứ 3 vào khiến agent bối rối và đọc trùng lặp nhiều hơn.

6. **Phương pháp nào tối ưu tổng thể về độ đúng, thời gian hoàn thành và chi phí?**
   - **Về cân bằng Tốc độ + Chi phí + Độ tin cậy hàng ngày:** **`ripgrep` (Arm B)** là tối ưu nhất (`58.2s` E2E, `77.4k` input, `271k` cache, `9 MB` RAM, `0s` indexing, `Recall = 0.9167`, `F1 = 0.6128`).
   - **Về Độ đầy đủ tối đa trên task phức tạp:** **`Adaptive v1` (`rg` + `CodeGraph`)** đạt **`100% Task Success (5/5)`**, `Recall = 0.9833` (chỉ sót 1/43 file), `F1 = 0.6263`, `12.8s` tới context liên quan — với điều kiện phải giữ quy tắc dừng chặt để tránh đọc dư (`20.2` `read_file`).

### Chiến lược sử dụng cuối cùng (đề xuất dựa trên dữ liệu Phase 1–3)
- **Mặc định cho mọi task tìm kiếm, regex, UI text, config, xuyên TS ↔ Python:** Dùng **`ripgrep` (`rg`)**.
- **Chỉ gọi `CodeGraph` (`explore` / `impact`) khi:** Cần truy vết luồng nhiều tầng (`API → Service → DB`) hoặc tính **Blast Radius** (`T4`, nơi CodeGraph chỉ tốn `36s` và `36k` tokens). Nên chạy qua MCP daemon để tránh độ trễ CLI.
- **Không tích hợp Graphify** vào workflow coding hàng ngày trên `hahlex-edu` (chỉ cân nhắc dùng riêng nếu có kho tài liệu/PDF/ảnh thiết kế lớn cần bắc cầu doc-to-code).
- **Điều kiện dừng:** Khi `rg` hoặc `codegraph` đã trả về đủ `critical_files` và chữ ký hàm cần thiết, dừng tìm kiếm và chỉ mở `read_file` 1 lần trên từng file đích (tránh đọc trùng lặp).

---

## 7. Artifacts & Dữ liệu Tái lập
- Script phân tích Phase 3: [`benchmarks/code-search/phase3/analyze_phase3.py`](../benchmarks/code-search/phase3/analyze_phase3.py)
- Dữ liệu chi tiết 30 phiên AI agent: [`benchmarks/code-search/phase3/phase3_results.json`](../benchmarks/code-search/phase3/phase3_results.json)
- Bảng tổng hợp theo 6 phương pháp: [`benchmarks/code-search/phase3/phase3_summary.json`](../benchmarks/code-search/phase3/phase3_summary.json)
- Môi trường Graphify cô lập: [`benchmarks/code-search/phase3/.venv`](../benchmarks/code-search/phase3/.venv) (cùng `graphify-out/` sinh cục bộ)
