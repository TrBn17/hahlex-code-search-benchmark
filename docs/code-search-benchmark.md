# Đánh giá & Benchmark Công cụ Tìm kiếm Mã nguồn: ripgrep vs CodeGraph trên Dự án LMS (`hahlex-edu`)

**Ngày thực nghiệm:** 2026-11-17  
**Phạm vi:** Đánh giá hiệu quả của `ripgrep` và `CodeGraph` đối với AI Coding Agent trên dự án LMS `hahlex-edu` (`education-platform` + `ai-platform`), so sánh với phương pháp tìm kiếm Baseline.

---

## 1. Môi trường và Phiên bản Công cụ

### 1.1. Phần cứng & Hệ điều hành
- **Hệ điều hành:** Microsoft Windows 11 Pro (`10.0.26200`)
- **CPU:** Intel(R) Core(TM) i5-14600KF (14 cores, 20 logical processors)
- **RAM:** 15.79 GB
- **Runtime:** Node.js `v24.22.1`, npm `11.19.1`, Python `3.11.15`, Git `2.52.0.windows.1`, Cargo `1.96.0`

### 1.2. Công cụ & Phiên bản đã cài đặt
| Công cụ | Phiên bản | Cách cài đặt | Ghi chú tương thích |
|---|---|---|---|
| **ripgrep (`rg`)** | `15.2.0` (`+pcre2`, SIMD `SSE2/SSSE3/AVX2`) | `winget install BurntSushi.ripgrep.MSVC` | Chạy native Windows, hỗ trợ `.gitignore` mặc định, không cần index |
| **CodeGraph (`codegraph`)** | `1.6.2` (extraction v27, `node-sqlite` WAL) | `npm i -g @colbymchenry/codegraph` | Chạy native Windows qua Rust kernel + SQLite; tạo thư mục `.codegraph/` |
| **Baseline (`git grep`)** | `git 2.52.0` | Có sẵn trong hệ thống | Cần chạy riêng cho từng sub-repo (`education-platform`, `ai-platform`) vì thư mục gốc không phải git repo |

> **Lưu ý cấu hình:** Theo yêu cầu không làm thay đổi workflow mặc định của agent trước khi hoàn tất đánh giá, chỉ cài đặt CLI (`rg` và `codegraph`) và khởi tạo index cục bộ (`.codegraph/`), **chưa chạy** `codegraph install` (không ghi vào `AGENTS.md`, `CLAUDE.md` hay cấu hình MCP toàn cục).

### 1.3. Quy mô Codebase & Chi phí Indexing của CodeGraph
Tổng số file không bị ignore (đo bằng `rg --files`): **6,072 files** (`education-platform`: 4,165 files; `ai-platform`: 1,765 files; phần còn lại ở thư mục gốc).

Kết quả khởi tạo index lần đầu (`codegraph init --yes .`):
- **Thời gian indexing ban đầu (wall-clock):** **71.22 giây** (bao gồm scan, parse AST bằng Tree-sitter/Rust kernel, resolve references, link dynamic dispatch và ghi SQLite).
- **Số lượng đã lập chỉ mục:** **4,906 files**, **114,773 nodes**, **387,040 edges** (trong đó có `31,826` functions, `32,046` imports, `5,177` methods, `2,189` classes, `1,600` interfaces, `1,011` framework routes).
- **Ngôn ngữ nhận diện:** `typescript`, `tsx`, `javascript`, `python`, `php`, `liquid`, `yaml`, `xml`, `properties`.
- **Dung lượng index trên đĩa (`.codegraph/`):** **477.16 MB** (`500,342,784 bytes`, SQLite WAL mode).
- **Thời gian incremental sync (`codegraph sync`, trung vị 3 lần trên repo sạch):** **843.86 ms** (lần 1: `8,769.91 ms`, lần 2: `839.47 ms`, lần 3: `843.86 ms`).

---

## 2. Phương pháp Benchmark và Đảm bảo Công bằng

### 2.1. Thiết kế 4 Phương pháp So sánh
1. **Baseline:** Mô phỏng agent không có `rg` và không có `codegraph`. Dùng `git -C <repo> grep -n -F` trên cả 2 repo (`education-platform` và `ai-platform`, loại trừ `*spec*` và `*test*`) kèm đọc tối đa 6 file khớp đầu tiên (120 dòng/file) để dựng context.
2. **ripgrep:** Dùng `rg -n --max-count 5` từ thư mục gốc (tự động quét cả `education-platform/apps` và `ai-platform/src` trong 1 lệnh, loại trừ `*.spec.*`, `*.test.*`, `**/test/**`, `**/__generated__/**`), kèm đọc tối đa 6 file khớp đầu tiên (120 dòng/file).
3. **CodeGraph:** Dùng các lệnh CLI tương đương MCP tools của CodeGraph (`codegraph explore`, `codegraph query --json`, `codegraph impact --json`, `codegraph callers --json`). Không cần bước đọc file riêng vì `explore` trả về source code kèm ngữ cảnh gọi hàm.
4. **Hybrid:** Kết hợp `rg -l` (tìm danh sách file nhanh theo từ khóa/regex) + `codegraph explore` hoặc `codegraph impact --json` (truy vết đồ thị gọi hàm và blast radius) + đọc tối đa 2 file bổ sung (80 dòng/file) nếu cần.

### 2.2. Cách đo lường & Đảm bảo Công bằng
- **Tái lập:** Toàn bộ kịch bản, ground truth và script đo được lưu tại [`benchmarks/code-search/tasks.json`](../benchmarks/code-search/tasks.json) và [`benchmarks/code-search/run_benchmark.py`](../benchmarks/code-search/run_benchmark.py).
- **Số lần chạy:** Mỗi cặp `(Task, Method)` chạy **3 lần độc lập** (tổng 60 lượt chạy), không dùng lại kết quả giữa các lần chạy. Không chỉnh sửa mã nguồn nghiệp vụ trong suốt quá trình benchmark.
- **Đo Token & Thời gian:**
  - `Search latency` và `End-to-end time` (mô phỏng thời gian thực thi tool & thu thập context, **không** bao gồm thời gian suy luận của LLM) được đo trực tiếp bằng `time.perf_counter()`.
  - `Payload tokens` (lượng token context nạp vào LLM từ output các tool) được đo chính xác bằng tokenizer `tiktoken` (`cl100k_base`).
  - **Giới hạn đo lường:** Do không chạy 60 phiên LLM API trả phí độc lập, **LLM Input/Output tokens thực tế và LLM thinking time** được ghi nhận là `N/A` (chỉ báo cáo chính xác **Context Payload Tokens** đo trực tiếp từ output công cụ).
  - `CPU time` (user + system) và `Peak RSS` (MB) được đo qua `psutil` trên tiến trình con.
- **Tiêu chí đánh giá chất lượng:**
  - **Precision / Recall / F1:** So sánh tập file production trả về với tập **Ground Truth** đã được kiểm chứng thủ công từ source code thực tế.
  - **Task Success:** Đạt chuẩn khi tìm đủ **100% các `critical_files`** VÀ **`Recall >= 0.60`**.

---

## 3. Danh sách 5 Task Thực nghiệm

| ID | Nhóm bài toán | Mô tả Task | Số file Ground Truth |
|---|---|---|---|
| **T1** | Tìm tính năng từ mô tả nghiệp vụ | Tìm vị trí triển khai tính năng **dự toán chi phí chấm bài AI (`ai-grading-estimate` / ước tính token/credit trước khi bấm 'Đồng ý chấm')** trên backend và các module gọi liên quan. | 5 |
| **T2** | Truy vết luồng API → Service → DB | Truy vết luồng **công bố bảng điểm (`publishGradebook`)** từ `GradebookController` qua tầng kernel (`publish.ts`, `load.ts`, `calc.ts`, `refusals.ts`) đến `db/schema.ts`. | 6 |
| **T3** | Điều tra bug liên quan nhiều module | Điều tra lỗi **từ chối tính năng hoặc trừ/hoàn credit AI grading không khớp** giữa `education` (`ai-grading-credits`, `approve.ts`) và `ai-bridge` (`feature-refusal`, `plan-features`, `ai-platform.client`). | 7 |
| **T4** | Phân tích ảnh hưởng (Blast Radius) | Xác định toàn bộ controller và module bị ảnh hưởng khi thay đổi signature/behavior của hàm **`offsetPage`** (`education/http/page-query.ts`). | 13 |
| **T5** | Tìm logic tương tự để tái sử dụng/refactor | Tìm tất cả các vị trí triển khai/sử dụng xác thực service-to-service (**`ServicePrincipalGuard` / `service-principal` / `service_auth`**) trên cả `education-platform` và `ai-platform`. | 12 |

---

## 4. Kết quả Đo đạc Thực nghiệm

### 4.1. Bảng tổng hợp trung bình / trung vị trên cả 5 Tasks (60 lượt chạy)

| Tiêu chí | Baseline (`git grep`) | ripgrep (`rg`) | CodeGraph (`codegraph`) | Hybrid (`rg` + `codegraph`) |
|---|---|---|---|---|
| **Tốc độ tìm kiếm (Median Search Latency)** | 427.00 ms | **83.81 ms** | 1,208.94 ms | 974.96 ms |
| **Tổng thời gian xử lý tool (Median E2E)** | 428.18 ms | **85.21 ms** | 1,208.94 ms | 977.63 ms |
| **Context Payload Tokens (Mean)** | 7,990.4 | **7,800.8** | 11,327.0 | 9,412.6 |
| **LLM Output Tokens** | N/A | N/A | N/A | N/A |
| **Số tool calls (Mean)** | 10.80 | 7.00 | **2.00** | 4.00 |
| **Precision / Recall (Mean)** | 0.6225 / 0.8381 | **0.6425 / 0.9048** | 0.3738 / 0.7747 | 0.3849 / 0.8714 |
| **F1 Score (Mean)** | 0.7111 | **0.7445** | 0.4973 | 0.5288 |
| **Task Success Rate** | 80% (4/5) | **100% (5/5)** | 60% (3/5) | 80% (4/5) |
| **Peak RAM (Median RSS)** | 45.18 MB | **8.99 MB** | 430.09 MB | 428.47 MB |
| **CPU Time (Median)** | 1,140.63 ms | **515.62 ms** | 1,234.38 ms | 1,500.00 ms |
| **Dung lượng Index trên đĩa** | 0 MB | 0 MB | 477.16 MB | 477.16 MB |
| **Điểm mạnh** | Không cần cài thêm; chính xác khi biết tên symbol trong 1 repo | Nhanh nhất (5.1× Baseline); tốn ít RAM nhất (9 MB); F1 & Success cao nhất | Giảm mạnh số tool calls (**2 calls**); tự truy vết call-graph đa tầng & blast radius | Kết hợp định vị nhanh của `rg` với đồ thị gọi hàm của `codegraph`, giảm số lần đọc file |
| **Hạn chế** | Phải gọi lặp cho từng repo/pattern (10.8 calls); bỏ sót cross-repo | Không hiểu AST/call-graph; phải tự mở đọc file và ghép luồng thủ công | Độ trễ CLI ~1.2s/lần (tốn ~430 MB RAM); output rộng làm giảm Precision và tăng payload tokens | Nếu chọn pattern `rg` thiếu (như T5) vẫn bị sót; mang theo chi phí RAM/index của CodeGraph |

### 4.2. Chi tiết theo từng loại Task

| Task | Method | Search (ms) | E2E (ms) | Tool Calls | Payload Tokens | Precision | Recall | F1 | Success |
|---|---|---|---|---|---|---|---|---|---|
| **T1** (Feature Discovery) | Baseline | 441.62 | 442.85 | 12 | 8,814 | 0.8333 | 1.0000 | 0.9091 | Pass |
| | ripgrep | **83.81** | **85.16** | 7 | 8,447 | **0.8333** | **1.0000** | **0.9091** | Pass |
| | CodeGraph | 1,241.49 | 1,241.49 | **2** | 9,860 | 0.3000 | 0.6000 | 0.4000 | Fail |
| | Hybrid | 1,029.02 | 1,029.48 | 4 | **8,268** | 0.3846 | **1.0000** | 0.5556 | Pass |
| **T2** (API → Service → DB) | Baseline | 300.88 | 304.61 | 10 | 9,451 | **0.4000** | 0.6667 | **0.5000** | Pass |
| | ripgrep | **91.96** | **94.58** | 7 | 8,659 | **0.4000** | 0.6667 | **0.5000** | Pass |
| | CodeGraph | 1,213.89 | 1,213.89 | **2** | **7,704** | 0.2500 | **0.8333** | 0.3846 | Pass |
| | Hybrid | 971.92 | 974.08 | 4 | 8,632 | 0.2500 | **0.8333** | 0.3846 | Pass |
| **T3** (Cross-Module Bug) | Baseline | 429.46 | 431.43 | 12 | 7,793 | **0.6667** | **0.8571** | **0.7500** | Pass |
| | ripgrep | **82.24** | **83.37** | 7 | 7,836 | **0.6667** | **0.8571** | **0.7500** | Pass |
| | CodeGraph | 1,323.33 | 1,323.33 | **2** | 9,672 | 0.4000 | **0.8571** | 0.5455 | Pass |
| | Hybrid | 1,122.78 | 1,123.40 | 4 | **7,702** | 0.4286 | **0.8571** | 0.5714 | Pass |
| **T4** (Impact / Blast Radius) | Baseline | 175.46 | 176.82 | 8 | 6,779 | **0.8125** | **1.0000** | **0.8966** | Pass |
| | ripgrep | **82.16** | **83.51** | 7 | **6,720** | **0.8125** | **1.0000** | **0.8966** | Pass |
| | CodeGraph | 679.84 | 679.84 | **2** | 19,651 | 0.6500 | **1.0000** | 0.7879 | Pass |
| | Hybrid | 399.80 | 400.46 | 4 | 14,594 | 0.5652 | **1.0000** | 0.7222 | Pass |
| **T5** (Similar Logic / Cross-Repo) | Baseline | 442.95 | 444.07 | 12 | **7,115** | 0.4000 | 0.6667 | 0.5000 | Fail |
| | ripgrep | **83.67** | **85.21** | 7 | 7,342 | **0.5000** | **1.0000** | **0.6667** | Pass |
| | CodeGraph | 1,189.07 | 1,189.07 | **2** | 9,748 | 0.2692 | 0.5833 | 0.3684 | Fail |
| | Hybrid | 971.46 | 972.04 | 4 | 7,867 | 0.2963 | 0.6667 | 0.4103 | Fail |

---

## 5. Phân tích Ưu Nhược điểm Theo Dữ liệu Thực nghiệm

1. **Tại sao `ripgrep` đạt F1 và Task Success cao nhất (100%), nhanh nhất (85 ms)?**
   - `hahlex-edu` là workspace **đa repo** (`education-platform` TypeScript/NestJS/React + `ai-platform` Python). `rg` quét xuyên cả hai repo chỉ trong **1 lệnh (~83 ms, ~9 MB RAM)**, hỗ trợ regex (`|`, `\b`) và glob loại trừ test (`--glob '!**/*.spec.*'`) cực kỳ gọn.
   - Ở **T5** (tìm xác thực service-to-service xuyên TS & Python), `rg` đạt Recall `1.00`, trong khi Baseline và CodeGraph đều không đạt ngưỡng thành công.

2. **Tại sao `CodeGraph` giảm được 71–81% số tool calls (2 calls vs 7–10.8) nhưng lại tốn nhiều token payload hơn và Precision thấp hơn?**
   - **Điểm mạnh thật sự của CodeGraph** thể hiện rõ nhất ở **T2 (Truy vết luồng API → DB)**: Recall của CodeGraph đạt **0.8333** (vượt cả `rg` và Baseline `0.6667`) chỉ với **2 tool calls** và **7,704 tokens** (thấp nhất trên T2), vì `codegraph explore` tự động đi theo cạnh gọi hàm từ `GradebookController` → `publishGradebook` → `loadGradebook` → `calc.ts` → `refusals.ts`.
   - **Điểm yếu đo được:**
     - `codegraph explore` mở rộng ngữ cảnh theo tên symbol gần đúng (ví dụ tìm `estimateTokens` trên T1 kéo theo các hàm `estimate` ở `tuition-overview.tool.ts` và `tool_output.py`), làm Precision giảm xuống `0.30` và bỏ sót `ai-messages.controller.ts` nếu không query tiếp.
     - `codegraph impact --json` trên T4 trả về payload JSON chi tiết tới **19,651 tokens** (gần gấp 3 lần `rg`).
     - Mỗi lần gọi CLI `codegraph` tốn **~1.2 giây** và **~430 MB RAM** để mở DB/graph (nếu chạy qua MCP daemon thường trực, độ trễ khởi động CLI sẽ giảm nhưng vẫn giữ RAM daemon).
     - Trên T5, CodeGraph không link được chuỗi string/decorator/kebab-case xuyên ranh giới HTTP giữa NestJS (`ServicePrincipalGuard`) và FastAPI (`service_auth.py`), dẫn đến Recall chỉ đạt `0.5833`.

3. **Ý nghĩa đối với AI Coding Agent thực tế:**
   - Trong thực tế, **1 lượt gọi LLM suy luận** thường tốn **1–5 giây**, nên việc CodeGraph giảm số vòng lặp tool-call từ `7–11 calls` xuống `2–4 calls` trên các bài toán truy vết luồng sâu (`T2`, `T4`) giúp giảm số lượt round-trip LLM đáng kể.
   - Ngược lại, dùng CodeGraph cho mọi tác vụ tìm kiếm đơn giản là **phản tác dụng** (chậm hơn `rg` ~14× về tool latency, tốn RAM/disk và nhồi context thừa).

---

## 6. Kết luận và Khuyến nghị Chiến lược Sử dụng

### 6.1. Trả lời các câu hỏi quyết định
1. **Có nên tích hợp CodeGraph và ripgrep vào workflow AI Coding Agent hiện tại không?**
   - **ripgrep (`rg`):** **NÊN tích hợp ngay làm công cụ tìm kiếm mặc định** (chi phí 0 MB disk, ~9 MB RAM, 84 ms, F1 cao nhất `0.7445`, Success `100%`).
   - **CodeGraph:** **NÊN tích hợp có chọn lọc (opt-in cho tác vụ đồ thị/truy vết)** nếu máy trạm đủ RAM/disk (477 MB disk, ~430 MB RAM). Không nên thay thế `rg` bằng CodeGraph cho tìm kiếm văn bản thông thường.
2. **Trường hợp nào nên ưu tiên ripgrep?**
   - Tìm vị trí triển khai theo từ khóa/regex, chuỗi UI tiếng Việt, biến môi trường, route string, pattern lặp lại xuyên repo TypeScript + Python (`T1`, `T5`).
3. **Trường hợp nào CodeGraph mang lại lợi thế rõ ràng?**
   - Truy vết luồng gọi hàm đa tầng từ API → Service → DB (`T2`), phân tích blast radius trước khi sửa hàm core (`T4`), hoặc tìm toàn bộ callers thực sự (loại bỏ comment/text trùng tên).
4. **Khi nào nên kết hợp cả hai (Hybrid)?**
   - Khi bắt đầu từ mô tả nghiệp vụ mơ hồ hoặc bug liên quan nhiều module (`T1`, `T3`): dùng `rg -l` (~85 ms) để định vị đúng file/tên symbol chính xác, sau đó gọi `codegraph explore <symbol>` (1 call) để lấy ngay call-path và danh sách test liên quan.
5. **Chi phí indexing và duy trì graph có đáng không?**
   - Indexing lần đầu mất **71.22s** và **477.16 MB** cho 4,906 files; incremental sync chỉ mất **~844 ms**. Với máy dev 16 GB RAM làm việc dài hạn trên `hahlex-edu`, chi phí này **chấp nhận được**; với CI/container nhẹ hoặc sửa nhỏ lẻ, chỉ cần `rg`.
6. **Có thực sự giảm token, tool calls và thời gian hoàn thành task không?**
   - **Tool calls:** Giảm rõ rệt (**2 calls** với CodeGraph, **4 calls** với Hybrid so với **7** của `rg` và **10.8** của Baseline).
   - **Context payload tokens:** **Không tự động giảm** khi dùng CodeGraph (tăng từ `7,801` lên `11,327` tokens do payload đồ thị rộng), trừ khi dùng đúng bài toán trace luồng (`T2`: `7,704` tokens) hoặc kết hợp `rg` lọc trước.
   - **Thời gian:** `rg` nhanh nhất ở tầng tool (`85 ms`); CodeGraph/Hybrid chỉ giúp giảm tổng thời gian E2E khi tiết kiệm được nhiều vòng lặp suy luận LLM.
7. **Có nên đặt chiến lược lựa chọn công cụ vào `AGENTS.md` không?**
   - **Có**, nhưng chỉ nên đưa **quy tắc định tuyến ngắn gọn (decision tree)** sau khi người dùng phê duyệt, không bắt buộc agent luôn gọi cả hai.

### 6.2. Quy trình Tự quyết định Công cụ (Đề xuất cho Hybrid Workflow)

```text
Nhận task tìm kiếm / phân tích code
  │
  ├─► Cần tìm theo text, regex, UI string, config, hoặc xuyên TS ↔ Python?
  │     └─► Dùng `ripgrep` (`rg -n` / `rg -l --glob '!*.spec.*'`)  [1 call, ~85ms]
  │
  ├─► Đã biết tên symbol, cần truy vết call-chain đa tầng hoặc blast radius?
  │     └─► Dùng `codegraph explore <symbol>` hoặc `codegraph impact <symbol>` [1 call]
  │
  └─► Chỉ có mô tả nghiệp vụ / bug đa module (chưa rõ tên symbol)?
        └─► Bước 1: `rg -l "<keyword>"` để chốt đúng file & symbol
            Bước 2: `codegraph explore <symbol>` để lấy call-path + callers + tests
```
