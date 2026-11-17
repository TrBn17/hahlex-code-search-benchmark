# Phase 2: Agent-Level Benchmark & Adaptive Code Search trên Dự án LMS (`hahlex-edu`)

**Ngày thực nghiệm:** 2026-11-17  
**Mục tiêu:** Đánh giá xem `ripgrep`, `CodeGraph`, và chiến lược `Adaptive Search` có thực sự giúp **AI Coding Agent độc lập** giải quyết các task LMS thực tế chính xác hơn, nhanh hơn và tiết kiệm token hơn so với workflow hiện tại hay không.

---

## 1. Kiểm tra lại Phase 1 (Audit)

Toàn bộ dữ liệu và script Phase 1 ([`benchmarks/code-search/results.json`](../benchmarks/code-search/results.json), [`summary.json`](../benchmarks/code-search/summary.json), [`docs/code-search-benchmark.md`](code-search-benchmark.md)) được giữ nguyên, không chỉnh sửa hay ghi đè. Qua rà soát mã nguồn [`run_benchmark.py`](../benchmarks/code-search/run_benchmark.py) và [`tasks.json`](../benchmarks/code-search/tasks.json):

1. **Cách tính Precision, Recall, Task Success và Tool Calls:**
   - Phase 1 đo **tool-level** (chạy deterministic CLI), không phải vòng lặp suy luận LLM.
   - `Baseline` (`git -C <repo> grep`) và `ripgrep` bị cố định bước đọc tối đa **6 file × 120 dòng**, dẫn đến số `tool_calls` bị chặn trên (7–12 calls) và `payload_tokens` bị giới hạn nhân tạo (~7,800–7,990 tokens), không phản ánh trường hợp agent thật phải đọc thêm hoặc dừng sớm.
   - `Task Success` trong Phase 1 yêu cầu tìm đủ `critical_files` và `Recall >= 0.60`.
2. **Xác minh Ground Truth:**
   - Tập `ground_truth_files` trong `tasks.json` được kiểm chứng từ source thực tế và tập trung vào file production (chưa tính các test file `.spec.ts` / `.e2e-spec.ts` hoặc frontend file ở T1/T4). Trong Phase 2, agent thật được phép báo cáo cả test và frontend nếu liên quan, và việc chấm điểm Recall vẫn đối chiếu trên cùng tập `ground_truth_files` production để đảm bảo công bằng giữa 4 arm.
3. **Phân biệt độ trễ tìm kiếm vs thời gian AI hoàn thành task:**
   - Phase 1 chỉ đo thời gian chạy lệnh (`83.8 ms` cho `rg` vs `1,208.9 ms` cho `codegraph`). Ở Phase 2, độ trễ công cụ chỉ chiếm một phần nhỏ trong tổng thời gian hoàn thành task (`47s – 199s`), phần lớn thời gian còn lại là **thời gian suy luận LLM qua nhiều turn** và **đọc/tổng hợp source code**.
4. **Vì sao Hybrid có kết quả thấp hơn ripgrep ở Phase 1:**
   - **Lỗi cấu hình pattern ở T5:** Trong `tasks.json`, `hybrid_rg` thiếu từ khóa `service-principal` (trong khi `rg_pattern` có), khiến Hybrid chỉ đạt `Recall = 0.67` (Fail T5).
   - **Gọi đồng thời cả hai công cụ theo mặc định:** `run_hybrid` luôn chạy `rg -l`, rồi chạy thêm `codegraph`, rồi đọc thêm 2 file. Output của `codegraph` kéo theo nhiều file lân cận (ví dụ 20–27 file ở T2, T4, T5), làm Precision tụt từ `0.6425` (`ripgrep`) xuống `0.3849` (`hybrid`) và `payload_tokens` tăng từ `7,800.8` lên `9,412.6`.

---

## 2. Thiết kế Adaptive Search

Để khắc phục nhược điểm "luôn gọi cả hai công cụ" của Hybrid Phase 1, **Adaptive Search** định tuyến theo loại task và chỉ leo thang khi cần:

| Loại Task | Chiến lược định tuyến | Điều kiện dừng & Giới hạn context |
|---|---|---|
| **1. Exact Search** (tên biến/hàm cụ thể, UI string, config, regex, xuyên TS ↔ Python) | **Chỉ dùng `ripgrep`** (`rg -n --max-count 5 --glob '!**/*.spec.*'`). | Dừng ngay khi xác nhận được các vị trí định nghĩa/gọi chính qua `read_file`. Không gọi `codegraph`. |
| **2. Symbol Navigation** (biết symbol, cần xem nơi dùng) | **Dùng `ripgrep` trước** (`rg -l`). Chỉ gọi `codegraph explore` nếu cần phân biệt caller thực sự với text/comment trùng tên. | Dừng khi đủ danh sách file gọi trực tiếp. |
| **3. Call-chain Tracing** (luồng API → Service → DB nhiều tầng) | **Ưu tiên `codegraph explore` trước** (`--limit 15`), dùng `read_file` để kiểm chứng query DB/logic chi tiết. | Dừng khi đã nối đủ 3 tầng Controller → Kernel/Service → DB tables. |
| **4. Impact Analysis** (blast radius khi sửa hàm/API) | **Dùng `codegraph impact` trước** để lấy cây phụ thuộc AST, sau đó gọi **`rg` 1 lần** để đối chiếu dynamic/string/config/test references. | Không đọc toàn bộ test files nếu chỉ cần danh sách ảnh hưởng; giới hạn `--limit 15`. |
| **5. Ambiguous Task** (mô tả nghiệp vụ mơ hồ, bug đa module) | **Tìm rộng bằng `rg -l`** theo từ khóa nghiệp vụ để chốt file/symbol; **chỉ mở rộng bằng `codegraph explore`** nếu `rg` chưa đủ nối luồng giữa các module. | Tối đa 12 tool calls (hướng dẫn chung); dừng ngay khi kiểm chứng đủ `critical_files` trên source thực tế. |

---

## 3. Thiết kế Benchmark AI Agent Thực tế

### 3.1. Thiết lập thử nghiệm công bằng
- **Môi trường:** Cùng commit sạch trên `D:\Projects\hahlex-edu` (`education-platform` + `ai-platform`), chỉ số `.codegraph/` đã dựng sẵn (`4,906` files, `114,773` nodes, `387,040` edges, `477.16 MB`).
- **Agent & Model:** Tạo subagent trung lập `bench-agent` (chỉ có `run_command` và `read_file`, cấm chỉnh sửa code) chạy trên **cùng model (`flash`)**, **20 phiên độc lập** (5 tasks × 4 arms), mỗi phiên bắt đầu từ context trống hoàn toàn:
  - **Arm A (Baseline):** Cấm `rg` và `codegraph`; chỉ dùng `git -C <repo> grep`, PowerShell và `read_file`.
  - **Arm B (ripgrep):** Dùng `rg` + `read_file`; cấm `codegraph`.
  - **Arm C (CodeGraph):** Dùng `codegraph` CLI (`explore`, `query`, `callers`, `callees`, `impact`, `node`) + `read_file` khi thiếu chi tiết; cấm `rg` và `git grep`.
  - **Arm D (Adaptive Search):** Áp dụng bảng định tuyến Adaptive Search ở Mục 2.
- **Đo lường trực tiếp:** Trích xuất trực tiếp từ `transcript.jsonl` / `transcript_full.jsonl` của từng phiên qua script [`benchmarks/code-search/analyze_agent_runs.py`](../benchmarks/code-search/analyze_agent_runs.py), lưu kết quả tại [`agent_results.json`](../benchmarks/code-search/agent_results.json) và [`agent_summary.json`](../benchmarks/code-search/agent_summary.json).

### 3.2. Giới hạn phương pháp đo
- Mỗi cặp `(Task, Arm)` chạy **1 phiên AI độc lập** (tổng 20 phiên) do chi phí/thời gian thực thi agent; chưa lặp lại 3 lần ở cấp agent như Phase 1.
- CodeGraph được gọi qua **CLI (`codegraph ...`)** thay vì **MCP daemon thường trực (`codegraph serve --mcp`)**, nên mỗi lần gọi chịu thêm chi phí khởi động tiến trình (~1.2s, ~430 MB RAM).
- Tất cả 5 task đều là **read-only investigation / impact analysis** (chưa chạy task sửa code + chạy unit/e2e test trên worktree riêng), nên chỉ số *"mức độ cần sửa lại"* được đánh giá qua số file ground truth bị bỏ sót và độ đầy đủ so với source thực tế.
- `Time to relevant context` được tính từ lúc bắt đầu phiên đến khi tool output của phiên đã chứa đủ 100% `critical_files` của task.

---

## 4. Kết quả Đo đạc AI Agent

### 4.1. Bảng tổng hợp trung bình trên 5 Tasks (20 phiên độc lập)

| Chỉ số | Arm A: Baseline | Arm B: ripgrep | Arm C: CodeGraph | Arm D: Adaptive |
|---|---|---|---|---|
| **Time to relevant context (Mean)** | 39.00 s | 28.60 s | 45.60 s | **23.40 s** |
| **Time to task completion (Mean)** | **79.80 s** | 103.60 s | 126.80 s | 92.20 s |
| **Số lượt LLM turns (Mean)** | **8.40** | 9.80 | 10.20 | 11.20 |
| **Tổng tool calls (Mean)** | **16.00** | 20.80 | 16.80 | 23.60 |
| — *Search commands* | 6.60 | **5.40** | 12.00 | 6.20 |
| — *`read_file` calls* | 9.40 | 15.40 | **4.80** | 17.00 |
| **Input tokens thực tế (Mean)** | 72,301.6 | **70,222.2** | 82,823.4 | 82,034.0 |
| **Cache read tokens (Mean)** | **314,756.4** | 354,752.2 | 461,681.2 | 504,697.0 |
| **Output tokens thực tế (Mean)** | 10,467.0 | 10,378.8 | 12,882.4 | **9,448.4** |
| **Context payload tokens (Mean)** | 34,511.0 | **32,618.0** | 38,691.0 | 42,116.0 |
| **Recall trên Ground Truth (Mean)** | **0.9381** | 0.8143 | 0.8667 | 0.9333 |
| **Precision file prod (Mean)** | 0.4866 | 0.4383 | 0.4646 | 0.4183 |
| **Tổng số file GT bị bỏ sót** | **2 / 43** | 7 / 43 | 5 / 43 | **2 / 43** |
| **Task Success Rate (strict path + R≥0.8)** | **100% (5/5)** | 60% (3/5) | 60% (3/5) | 80% (4/5) |

> **Lưu ý kiểm chứng thủ công ở T2:** Trong `T2`, cả Arm B (`ripgrep`), Arm C (`CodeGraph`) và Arm D (`Adaptive`) đều có nhắc tới `calc.ts` và `refusals.ts` theo tên ngắn (`calc.ts:510`, `refusals.ts:99`) trong phần mô tả `kernel/gradebook/`, nhưng parser đường dẫn đầy đủ chỉ tính khi có đường dẫn đầy đủ nên ghi nhận thiếu 2 file này; riêng Arm C (`CodeGraph`) thực sự **không mở `db/schema.ts`** mà chỉ đọc tên bảng Drizzle từ `publish.ts`/`load.ts`. Nếu tính cả các file đã nêu đúng theo tên ngắn trong cùng thư mục `gradebook/`, tỷ lệ hoàn thành nghiệp vụ đạt: Baseline 5/5, Adaptive 5/5, ripgrep 4/5 (thiếu ở T3), CodeGraph 3/5 (thiếu `db/schema.ts` ở T2 và 2 file ở T5).

### 4.2. Kết quả chi tiết từng Task

| Task | Arm | Ctx Time | E2E Time | Turns | Tools (Search / Read) | Input Tokens | Output Tokens | Recall GT | Missed GT |
|---|---|---|---|---|---|---|---|---|---|
| **T1** (Feature Discovery) | Baseline | 47.0 s | 87.0 s | 10 | 20 (9 / 11) | 75,039 | 6,787 | **1.00** | 0 |
| | ripgrep | **12.0 s** | 106.0 s | 10 | 21 (4 / 17) | 67,499 | 8,470 | **1.00** | 0 |
| | CodeGraph | 69.0 s | 108.0 s | **7** | **15** (15 / 0) | **46,487** | 8,531 | **1.00** | 0 |
| | Adaptive | 14.0 s | **39.0 s** | **7** | 18 (2 / 16) | 58,796 | **6,562** | **1.00** | 0 |
| **T2** (API → Service → DB) | Baseline | 99.0 s | 109.0 s | 10 | 25 (5 / 20) | 74,954 | 8,875 | **0.83** | 1 (`refusals.ts`) |
| | ripgrep | **6.0 s** | 87.0 s | **8** | **17** (3 / 14) | 61,387 | 8,169 | 0.67* | 2* (`calc.ts`, `refusals.ts`) |
| | CodeGraph | 52.0 s | **54.0 s** | **8** | 18 (7 / 11) | **49,307** | **7,628** | 0.50* | 3* (`schema.ts` + 2) |
| | Adaptive | 78.0 s | 133.0 s | 13 | 22 (7 / 15) | 76,800 | 8,097 | 0.67* | 2* (`calc.ts`, `refusals.ts`) |
| **T3** (Cross-Module Bug) | Baseline | 24.0 s | **77.0 s** | 8 | **11** (4 / 7) | 91,895 | 14,807 | 0.86 | 1 (`ai-grading-estimate.ts`) |
| | ripgrep | 55.0 s | 112.0 s | **7** | 12 (2 / 10) | **63,627** | **12,063** | 0.57 | 3 (`ai-platform.client`, `estimate`, `features`) |
| | CodeGraph | 9.0 s | 190.0 s | 16 | 26 (15 / 11) | 172,119 | 21,766 | **1.00** | **0** |
| | Adaptive | **4.0 s** | 78.0 s | 13 | 33 (4 / 29) | 137,958 | 12,628 | **1.00** | **0** |
| **T4** (Blast Radius `offsetPage`) | Baseline | **3.0 s** | **79.0 s** | **7** | **12** (10 / 2) | **48,242** | 11,599 | **1.00** | 0 |
| | ripgrep | 5.0 s | 84.0 s | 11 | 28 (12 / 16) | 74,119 | 13,006 | **1.00** | 0 |
| | CodeGraph | 15.0 s | 199.0 s | 15 | 14 (12 / 2) | 90,906 | 14,578 | **1.00** | 0 |
| | Adaptive | 15.0 s | 113.0 s | 11 | 18 (13 / 4) | 59,851 | **9,455** | **1.00** | 0 |
| **T5** (Cross-Repo Auth) | Baseline | 22.0 s | **47.0 s** | 7 | 12 (5 / 7) | 71,378 | 10,267 | **1.00** | **0** |
| | ripgrep | 65.0 s | 129.0 s | 13 | 26 (6 / 20) | 84,479 | **10,186** | 0.83 | 2 (`context.ts`, `platform-quality-tracing`) |
| | CodeGraph | 83.0 s | 83.0 s | **5** | **11** (11 / 0) | **55,298** | 11,909 | 0.83 | 2 (`mcp.controller`, `platform-quality-tracing`) |
| | Adaptive | **6.0 s** | 98.0 s | 12 | 27 (5 / 21) | 76,765 | 10,500 | **1.00** | **0** |

### 4.3. Phân tích sâu những phát hiện quan trọng
1. **Nghịch lý Baseline nhanh nhất về E2E (`79.8s`) và ít `tool_calls` nhất (`16.0`):**
   - Trên dự án `hahlex-edu` (quy mô ~6,000 files, cấu trúc module rõ ràng), `git grep` chỉ mất ~200–400 ms và ép agent phải mở file mục tiêu bằng `read_file` ngay (`9.4` lần đọc). Trong khi đó, việc có `rg` hoặc `codegraph` với nhiều flag tùy chọn khiến agent có xu hướng **chạy nhiều lệnh kiểm tra chéo hơn** (`20.8` calls ở `ripgrep`, `23.6` calls ở `Adaptive`), làm tăng `cache_read_tokens` (`504k` ở `Adaptive` vs `314k` ở `Baseline`).
2. **Giá trị thật sự của `CodeGraph` bộc lộ ở T3 (Bug đa module) & T4 (Impact Analysis):**
   - Ở **T3**, `ripgrep` chỉ dùng 2 lệnh search rồi đọc 10 file và **bỏ sót 3/7 file quan trọng** (`Recall = 0.57`, không phát hiện đủ chuỗi `ai-platform.client.ts` ↔ `features.ts` ↔ `ai-grading-estimate.ts`). Ngược lại, `CodeGraph` và `Adaptive` tìm được **100% (7/7 file)**, đạt `time_to_relevant_context` chỉ **4s – 9s** và phát hiện thêm hàng loạt điểm lệch thực tế (`CrmOutboxWorker`, `auto-retry.ts`, `regrade.ts`, `Superadmin` bypass lệch với background worker).
   - Ở **T4**, `Adaptive` (`codegraph impact` + `rg`) tìm ra cả **5 downstream frontend consumers** (`setupSteps.ts`, `educationQueries.ts`, v.v.) mà `Baseline` và `ripgrep` ít chú ý.
   - Tuy nhiên, khi ép dùng `CodeGraph` **đơn độc** (không có `rg`), agent phải gọi CLI `codegraph` tới `12` lần/task (tốn `126.8s` E2E và `82.8k` input tokens) và vẫn bị sót ở **T5** (không tìm được các file chỉ import hằng số hoặc chuỗi header qua ranh giới HTTP TS ↔ Python).
3. **`Adaptive Search` nhanh nhất khi định vị context (`23.4s`) và đầy đủ nhất (`0` file bị bỏ sót ở T1, T3, T4, T5), nhưng chưa tối ưu chi phí token/tool calls:**
   - So với `ripgrep` thuần: `Adaptive` nhanh hơn về E2E (`92.2s` vs `103.6s`), định vị context nhanh hơn (`23.4s` vs `28.6s`), Recall cao hơn hẳn (`0.9333` vs `0.8143`), Output tokens thấp hơn (`9,448` vs `10,379`), nhưng **tốn thêm ~17% Input tokens** (`82,034` vs `70,222`) và **nhiều `read_file` hơn** (`17.0` vs `15.4`).
   - Nguyên nhân: Agent ở Arm D vẫn đọc quá nhiều file sau khi đã có kết quả từ `codegraph explore`/`rg`, chưa tuân thủ triệt để điều kiện dừng sớm.

---

## 5. Kết luận và Đề xuất

### Trả lời 5 câu hỏi cốt lõi

1. **`ripgrep` có thực sự tốt hơn Baseline khi AI Agent tham gia hay không?**
   - **Có về tốc độ định vị context (`28.6s` vs `39.0s`), số lệnh search (`5.4` vs `6.6`) và Input tokens (`70.2k` vs `72.3k`)**, đặc biệt vì quét xuyên cả `education-platform` + `ai-platform` trong 1 lệnh.
   - **Nhưng chưa chắc tốt hơn về E2E time (`103.6s` vs `79.8s`) và Recall (`0.8143` vs `0.9381`)** nếu agent tự tin quá sớm vào kết quả text search và dừng tìm ở các bài toán bug đa module như T3.

2. **`CodeGraph` có giúp giải quyết những task phức tạp mà `ripgrep` gặp khó khăn không?**
   - **Có, rất rõ ở T3 (Bug đa module `education` ↔ `ai-bridge` ↔ `ai-platform`) và T4 (Blast radius xuyên backend → frontend).** CodeGraph đạt `Recall = 1.00` ở T3 trong khi `ripgrep` chỉ đạt `0.57`, và `codegraph explore` ở T1/T5 hoàn thành mà cần `0` lần `read_file` bổ sung.
   - Tuy nhiên, dùng CodeGraph **một mình** (cấm `rg`) cho mọi task là **kém hiệu quả** (`126.8s` E2E, `82.8k` input tokens, `430 MB` RAM mỗi lần gọi CLI, `477 MB` đĩa).

3. **`Adaptive Search` có cải thiện chất lượng và giảm tổng chi phí so với chỉ sử dụng `ripgrep` không?**
   - **Cải thiện rõ chất lượng & tốc độ:** Recall tăng từ `0.8143` → **`0.9333`**, `Time to relevant context` giảm từ `28.6s` → **`23.4s`**, E2E giảm từ `103.6s` → **`92.2s`**, Output tokens giảm từ `10,379` → **`9,448`**.
   - **Chưa giảm được Input/Cache tokens:** Input tokens tăng từ `70.2k` → `82.0k` (+16.8%) và `cache_read_tokens` tăng từ `354.8k` → `504.7k` (+42.3%) do agent vẫn gọi thêm nhiều `read_file` (trung bình 17 lần) sau bước tìm kiếm. Cần siết chặt hơn ngưỡng dừng và không đọc lại file nếu `codegraph explore` đã trả verbatim source.

4. **Khi nào nên gọi `CodeGraph`, và khi nào không?**
   - **NÊN gọi CodeGraph khi:**
     - Điều tra bug hoặc luồng nghiệp vụ đi qua **nhiều module / nhiều lớp** (`T3`, `T2` — đặc biệt khi `rg` trả quá nhiều kết quả hoặc bỏ sót caller gián tiếp).
     - Phân tích **Blast Radius / Impact Analysis** trước khi đổi signature hàm core dùng rộng rãi (`T4`, kèm 1 lần `rg` kiểm tra string/config/test).
     - Cần giảm số lượt `read_file` khi chạy qua **MCP server** (`codegraph serve --mcp`), tránh chi phí spawn CLI 1.2s/lần.
   - **KHÔNG nên gọi CodeGraph khi:**
     - Tìm chuỗi văn bản, UI tiếng Việt, env var, route string, hằng số header xuyên ngôn ngữ TS ↔ Python (`T5`) → dùng `rg`.
     - Tìm vị trí triển khai khi đã biết tên symbol/từ khóa hẹp (`T1`) → dùng `rg` + `read_file` là đủ và nhanh hơn.
     - Môi trường hạn chế RAM/đĩa (không muốn giữ index `477 MB` và tiến trình `~430 MB` RAM).

5. **Có đáng bổ sung chiến lược này vào `CLAUDE.md` hoặc `AGENTS.md` không?**
   - **Đáng bổ sung `ripgrep` + quy tắc định tuyến ngắn gọn (không cài `codegraph` làm công cụ bắt buộc mặc định)**, với 2 điều kiện:
     1. Nếu tích hợp `CodeGraph`, **nên dùng qua MCP server** (`codegraph serve --mcp`) để bỏ độ trễ khởi động CLI ~1.2s/lần và hạn chế gọi CLI lặp lại, thay vì chạy `codegraph` qua shell.
     2. Chỉ ghi **3 dòng quy tắc chọn công cụ** vào `AGENTS.md` / `CLAUDE.md` (mặc định `rg`; dùng `codegraph explore`/`impact` cho multi-module trace & blast radius; không đọc lại file nếu `explore` đã trả source) để tránh làm phình system prompt và token đầu vào.

---

## 6. Artifacts & Dữ liệu Tái lập
- Script phân tích transcript agent: [`benchmarks/code-search/analyze_agent_runs.py`](../benchmarks/code-search/analyze_agent_runs.py)
- Dữ liệu chi tiết 20 phiên AI agent: [`benchmarks/code-search/agent_results.json`](../benchmarks/code-search/agent_results.json)
- Bảng tổng hợp theo phương pháp: [`benchmarks/code-search/agent_summary.json`](../benchmarks/code-search/agent_summary.json)
- Bộ task & ground truth dùng chung với Phase 1: [`benchmarks/code-search/tasks.json`](../benchmarks/code-search/tasks.json)
