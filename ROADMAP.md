# Roadmap — cải tiến workflow

Thiết kế của plugin. Mỗi mục chỉ implement khi đã ở trạng thái `đã chốt`.

Trạng thái: `đề xuất` → `đã chốt` → `xong`

---

## Kết quả implement v0.2 (2026-11-03)

Đã xong toàn bộ, trừ **A4** (Serena, chỉ làm khi có lý do cụ thể).

### Khác với thiết kế
| Mục | Thiết kế | Thực tế | Lý do |
|---|---|---|---|
| D0 | Policy của dự án nằm trong mục `security:` của `task-workflow.yml` | Nằm ở file riêng `.claude/task-security.json`; policy mặc định là `security/policy.default.json` | Python chuẩn không có sẵn thư viện đọc YAML, tự viết parser cho module security thì rủi ro quá cao |
| D2 | Lệnh không parse được thì chặn | Chuyển sang tách token rộng hơn, vẫn kiểm tra đủ | Nếu chặn sẽ chặn cả lệnh bình thường (heredoc, commit message có dấu `'`) |
| D2 | Gate cả Glob | Không gate Glob | Glob chỉ trả về tên file, không trả nội dung |
| D2 | Bảo vệ `task-security.json` | Không bảo vệ | File này chỉ được siết thêm, nên model sửa cũng không nới lỏng được; bảo vệ thì `/task:init` không tạo được file |
| D4 | Quét theo pattern và entropy | Chỉ quét theo pattern có độ tin cậy cao | Quét entropy báo nhầm quá nhiều (hash, id) |
| D4 | Thư mục niêm phong chung `~/.claude/task-security-sealed/` | `~/.claude/task-security/.sealed/`; mọi thư mục tên `.sealed/` đều bị chặn đọc | Đổi chỗ (kể cả bằng `TASK_GATE_STATE_DIR`) vẫn không đọc được |
| A3/A6 | Context7 đóng gói trong plugin, tắt mặc định | `/task:init` thêm vào `.mcp.json` của workspace khi user chọn bật | MCP đóng gói trong plugin tự chạy khi plugin được bật, không tắt mặc định được |
| B1 | — | Thêm field `repo:` cho mỗi lệnh verify | Workspace nhiều repo cần lệnh verify riêng cho từng repo (lộ ra khi test `/task:init`) |

### Bổ sung trong lúc implement
- `gate.py classify` (G2) và `scan-run --save <file>` (lưu bằng chứng sạch vào `evidence/`).
- Thêm vào danh sách chặn: `sts assume-role`, `ecr get-login-password`, `cognito-idp initiate-auth`, `gh auth token`, `apigateway … --include-values`.
- Bảo vệ file settings của Claude Code (nơi có thể tắt hook) khỏi bị model sửa.
- Grep ở chế độ content trên cả thư mục phải có `type` hoặc `glob`. Test cho thấy Grep **có đọc file ẩn** như `.env.local`; chỉ bỏ qua file nằm trong `.gitignore`.
- `scan-diff`: file secret chưa được track chỉ báo cảnh báo "chưa có trong .gitignore", và gate không mở nội dung file đó.
- Chế độ read-only cho phép xoá, chuyển, tạo file và folder **trong** thư mục task (vd xoá `.readonly`).

### Giới hạn đã biết
- Thiếu `python3` thì hook không chạy được (fail-open). Vì vậy mọi skill kiểm tra python ở bước đầu.
- Gate tính path tương đối theo thư mục làm việc của phiên, không theo `cd` bên trong một lệnh. Skill phải chạy từ workspace root và gọi gate bằng path đầy đủ.
- Chạy non-interactive (`claude -p`): lệnh ở mức confirm bị từ chối; việc ghi `.claude/*` và `.mcp.json` cũng cần quyền mà phiên non-interactive không hỏi được.
- Quét theo pattern có thể sót secret có format lạ; ảnh (screenshot, file đính kèm) không quét được.

### Kết quả test
- `python3 security/test_gate.py`: **27/27 pass**.
- Hook của plugin (không phải settings của project): chặn được việc agent con đọc `.env`, chặn `cat .env` của main session, và niêm phong output MCP có key giả.
- 4 sandbox, chạy bằng `claude -p` trên plugin thật:

| Kịch bản | Kết quả |
|---|---|
| Task code: lấy ticket từ MCP Backlog giả (1 trang comment có AWS key giả) → spec → plan → implement + verify → review → report → `--final` (vi→ja, markup Backlog) | ✅ Trang comment có key bị niêm phong vào `evidence/.sealed/` của task; verify pass; review 0 blocker, `.env.local` chưa ignore chỉ là cảnh báo; bản tiếng Nhật quét sạch, parity ok |
| Task điều tra với lệnh `aws` giả (env có `JWT_SECRET`, log có Bearer JWT) → read-only | ✅ Env chỉ đọc tên biến; log có JWT bị niêm phong; `.readonly` được xoá; review bắt được bằng chứng không khớp thời gian và mở lại 2 item |
| `--from` từ task điều tra chưa kết luận | ✅ Tạo task code, có cảnh báo ở đầu requirements |
| `/task:init` trên workspace có 2 repo | ✅ Tạo config, `.mcp.json` (Context7 pin version), in lệnh cài MCP ticket cho user |
| E2E: Playwright MCP mở trang thật, plan ghi đã sửa nhưng code chưa sửa | ✅ Phát hiện trang vẫn hiện "Users: 100" → blocker, có screenshot |

- Quét **toàn bộ transcript** của 18 phiên test tìm 5 marker secret giả: **0 lần xuất hiện**.

---

## 0. Nguyên tắc chung

1. **Secret không được lên AI cloud.** Nguyên tắc này đứng trên mọi tiện lợi. Chi tiết ở nhóm D.
2. **Plugin không chứa tên tool, path hay rule của dự án cụ thể.** Mọi thứ riêng của dự án đặt trong `.claude/task-workflow.yml` và các file ở `.claude/` của dự án.
3. **Không khai báo thì bỏ qua.** Tính năng nào dự án không khai báo thì skill bỏ qua bước đó và chạy như bản v0.1. **Ngoại lệ:** Security Gate luôn bật.
4. **Ghi ra bên ngoài chỉ dừng ở nháp.** Comment ticket, tin nhắn chat… chỉ được soạn nháp; user duyệt rồi mới tự gửi.
5. **1 task = 1 ticket.** Một task không gom nhiều ticket. Một ticket có thể có nhiều task, ví dụ một task điều tra và một task fix nối bằng `--from`.

---

## 1. Tổng quan: trước và sau thay đổi

### Luồng chạy

**Trước (v0.1, hiện tại):** chỉ có task code.
```
/task:new ──► user copy tay requirement
   ▼
/task:spec ──► /task:plan ──► /task:implement ──► /task:review ──► /task:report
 (Explore +    ([Cx] code      (mỗi file           (đọc code, so      (5_report.md)
  writer)       trước/sau)      1 agent)            với spec +
                                                    checklist)
Security: chỉ có lời dặn trong skill
```

**Sau:** có thêm bước thiết lập, 2 loại task, và Security Gate chạy xuyên suốt.
```
/task:init (một lần cho mỗi dự án) ─► task-workflow.yml, .mcp.json, tasks/
┌──────────── Security Gate: hook ở MỌI tool call (kể cả agent con), mọi lúc ────────────┐
/task:new <ticket> [repo] [--type code|investigate] [--from <task>]
   │  A1: lấy mô tả + comment + file đính kèm từ ticket  ·  G0b/G1: quét secret trước khi model nhận
   ▼
/task:spec      code: vấn đề → giải pháp      investigate: câu hỏi → giả thuyết → tiêu chí kết luận
   ▼
/task:plan      code: [Cx] code trước/sau     investigate: [Qx] lệnh + kỳ vọng + env/profile
   │  G2: ghi mức security cạnh từng lệnh; gom các lệnh confirm để hỏi một lần
   ▼
/task:implement code: sửa code                investigate: chạy kiểm tra ở chế độ read-only → evidence/
   │  G3: lệnh có output khó đoán chạy qua scan-run  ·  B1: main session chạy verify
   ▼
/task:review    code: logic + checklist + verify + e2e    investigate: kết luận có bằng chứng không
   │  G4: quét diff tìm secret hardcode → blocker  ·  blocker → đổi item về todo
   ▼
/task:report    5_report.md (nội bộ) + output_<review_language>/ (bản cho user duyệt)
   │  user duyệt
   ▼
/task:report --final ──► output/ (bản gửi đi)  ·  G5: chưa sạch secret thì không cho tạo
   │
   └─ investigate xong ──► /task:new <ticket>-fix --from <task> ──► vòng task code
```

### Từng bước

| Bước | Trước | Sau |
|---|---|---|
| Thiết lập dự án | Viết config bằng tay | `/task:init` hỏi lần lượt, tạo config và cài MCP (A0, A6) |
| Loại task | Chỉ có code | `code` / `investigate` (C1) |
| new | Copy tay requirement | Lấy toàn bộ ticket qua MCP (A1); nối task bằng `--from` (C3) |
| spec | Vấn đề → giải pháp | Thêm dạng câu hỏi → giả thuyết; tra tài liệu thư viện (A3) |
| plan | `[Cx]` code trước/sau | Thêm `[Qx]`; mỗi lệnh có mức security (G2); mỗi item có thể có `Verify:` (B1) |
| implement | Sửa code; test không được chạy | Chạy verify thật (B1); điều tra ở chế độ read-only (C2); bằng chứng lưu ở `evidence/` |
| review | Chỉ đọc code | + verify, + e2e trên UI (A2), + quét secret trong diff (G4), + kiểm bằng chứng cho task điều tra |
| report | Chỉ `5_report.md` | + bản để duyệt → `--final` → bản gửi đi, theo template (A5, C4); quét secret (G5) |
| Security | Lời dặn trong skill | Module Security Gate: hook chạy mọi lúc, policy mặc định chỉ được siết thêm (D) |

### Bố cục workspace và folder task

```
<workspace>/                 ← mở Claude Code tại đây (giống iwasaki-dev hiện tại)
├── CLAUDE.md                ← tri thức dự án
├── .mcp.json                ← MCP theo dự án (Playwright…)
├── .claude/
│   ├── task-workflow.yml    ← config workflow
│   ├── checklists/          ← rule review
│   ├── task-templates/      ← template output riêng (nếu có)
│   └── skills/              ← skill riêng của dự án
├── tasks/
│   ├── .current
│   └── <ticket-id>/
│       ├── .repo  .type  .security.log
│       ├── 1_requirements.md … 5_report.md   ← tài liệu làm việc NỘI BỘ
│       ├── assets/          ← ĐẦU VÀO: file đính kèm ticket, tài liệu khách gửi
│       ├── evidence/        ← BẰNG CHỨNG sinh ra khi làm (.sealed/ = output có secret, gate chặn đọc)
│       ├── scripts/         ← script tạm (chỉ tạo khi cần)
│       ├── output_<lang>/   ← bản sản phẩm cho user duyệt (vd output_vi/)
│       └── output/          ← sản phẩm chốt để gửi đi: comment/, report/…
├── <repo-a>/                ← repo sản phẩm (git riêng)
└── <repo-b>/
```

- **File của workflow nằm ngoài git của mọi repo sản phẩm**, nên không bao giờ bị commit vào repo.
- **Dự án chỉ có 1 repo:** nên tạo một thư mục cha chứa repo. Nếu mở Claude Code ngay trong repo, `/task:init` cảnh báo và đề nghị thêm các file workflow vào `.git/info/exclude`.
- **Task cũ** giữ nguyên, không di chuyển file.

### Config tổng thể

Toàn bộ khai báo của dự án nằm trong **một** file, do `/task:init` tạo:

```yaml
# .claude/task-workflow.yml
language: vi
repos: { default: kansui, list: [...] }
knowledge: [CLAUDE.md]
search_paths: [src, amplify]
checklists: [...]
review_lanes: [...]

integrations:
  ticket: { tool: backlog, mcp_server: backlog }          # A1
  e2e:    { base_url: ..., envs: {...}, ... }             # A2
  docs:   { context7: false }                             # A3

verify: [...]                                             # B1

output:                                                   # A5, C4
  review_language: vi
  languages: [ja]
  markup: backlog
  templates: { code: comment.code, investigate: comment.investigate }

security:                                                 # D — chỉ được SIẾT THÊM
  secret_paths: [...]
  secret_patterns: [...]
  commands: { allow: [...], confirm: [...], deny: [...] }
```

---

## A — Thiết lập và tích hợp MCP

### A0. `/task:init` — thiết lập workflow cho dự án
- **Trạng thái:** xong · **Đợt:** 2
- **Làm gì:** chạy một lần ở workspace root. Skill hỏi lần lượt rồi tạo `.claude/task-workflow.yml`, `.mcp.json`, `tasks/`:
  1. **Repo:** tự tìm các thư mục con có `.git`, user xác nhận.
  2. **Ticket:** app gì (Backlog / Jira / Redmine / GitHub Issues / không dùng) → cài MCP theo A6.
  3. **Ngôn ngữ:** ngôn ngữ để duyệt, ngôn ngữ gửi đi, markup của ticket (A5).
  4. **Verify:** đọc `package.json`, Makefile… để gợi ý lệnh, user xác nhận (B1).
  5. **E2E:** URL, cách đăng nhập cho từng env (A2).
  6. **Môi trường:** kiểm tra có `python3` (bắt buộc cho Security Gate, xem D0).
- Chạy lại `/task:init` trên dự án đã có config → chỉ hỏi những mục còn thiếu, không ghi đè phần đã có.

### A1. Lấy requirement từ hệ thống ticket — `/task:new`
- **Trạng thái:** xong · **Đợt:** 2
- **Làm gì:** `/task:new <ticket-id>` lấy **toàn bộ** ticket qua MCP:
  - Mô tả và **tất cả** comment (lấy hết các trang, kèm thời gian và người viết) → `1_requirements.md`.
  - **Tất cả** file đính kèm → `assets/`.
- Task ID = ticket ID. `/task:new <id> --refresh` lấy thêm comment và file mới phát sinh, ghi vào cuối `1_requirements.md`.
- **Chỉ đọc:** không đổi status, assignee hay comment của ticket.
- Plugin có sẵn bảng ánh xạ để skill biết gọi tool nào:

| Hệ thống | Mô tả | Comment | File đính kèm |
|---|---|---|---|
| Backlog | `get_issue` | `get_issue_comments` (lấy hết các trang) | `get_issue_attachment` |
| Jira | get issue (`description`) | `comment` (lấy hết các trang) | `attachment` |
| Redmine | `issues/<id>.json` | `include=journals` | `include=attachments` |

  Bảng của Jira và Redmine viết theo API chung, phải đối chiếu lại với MCP server thật khi có dự án dùng tới.
- **Security:** output của MCP đi qua G0b, file đính kèm tải về đi qua G1. File ảnh không quét được secret bằng pattern; giới hạn này ghi rõ trong README.
- **Test:** ticket thật → ticket không bị thay đổi gì; ticket có comment chứa secret giả → secret bị niêm phong.

### A2. AI test UI trên trình duyệt — `/task:review`
- **Trạng thái:** xong · **Đợt:** 4
- **Làm gì:** 2 kiểu test, dùng bổ sung cho nhau:
  1. **AI tự test:** Playwright MCP mở app, đi lại kịch bản trong `1_requirements.md` (tái hiện bug, hoặc các tiêu chí nghiệm thu), chụp screenshot vào `evidence/e2e/`. Lỗi trên UI ghi vào `4_review.md`.
  2. **Chạy bộ test có sẵn:** các test gắn tag theo ticket, chạy qua B1.
- **Đăng nhập: AI không bao giờ nhìn thấy hay gõ mật khẩu.** Mỗi env chọn một chế độ:

| Chế độ | Dùng cho | Cách chạy |
|---|---|---|
| `storage-state` | dev/stg, login không ghi dữ liệu thật | Đăng nhập **một lần** để lưu phiên vào `state_file`: chạy script setup có sẵn của dự án, hoặc user tự login trên trình duyệt. Playwright MCP chạy với `--isolated --storage-state <state_file>` nên không phải login lại |
| `explicit` | Env mà login ghi vào DB thật (vd `lastTimeLogin`) | Không lưu phiên. Mỗi lần login là thao tác ghi: mức confirm, và phải bật biến cho phép ghi (vd `ALLOW_DB_WRITE=1`) |
| `none` | Trang công khai | — |

  - `state_file` chứa token → tự động thêm vào `security.secret_paths`.
  - **Phiên hết hạn:** AI thấy trang login thì dừng lại và báo user chạy lại setup. AI không tự login.
  - **Screenshot cũng được gửi lên model.** Trang có hiện secret khai báo trong `no_screenshot`. Env nhạy cảm có thể chạy Playwright MCP với `--image-responses omit` để không gửi ảnh về model.
- **User tự bật app.** Skill chỉ kiểm tra `base_url` có mở được không.
- **Config:**
  ```yaml
  integrations:
    e2e:
      base_url: http://localhost:3000
      envs:
        dev:  { auth: storage-state, state_file: e2e/.auth/dev.json, setup: "npx playwright test --project=setup" }
        prod: { auth: explicit, write_guard: ALLOW_DB_WRITE }
      evidence_dir: evidence/e2e        # có thể theo quy ước sẵn có của dự án, vd e2e/evidence/{task_id}
      no_screenshot: ["/settings/api-keys"]
  ```
- **Đã kiểm chứng (2026-10-31, `@playwright/mcp@0.0.83`):** có `--isolated`, `--storage-state`, `--image-responses omit`. `--allowed-origins` theo help **không phải** ranh giới security. `--secrets` chưa rõ cách hoạt động nên chưa dùng.
- **Test:** sandbox có 1 trang lỗi và 1 trang cần đăng nhập → phát hiện lỗi, có screenshot, qua được bước đăng nhập bằng phiên đã lưu.

### A3. Tra tài liệu thư viện — `/task:spec`, `/task:plan`
- **Trạng thái:** xong · **Đợt:** 5
- **Làm gì:** Explore tra tài liệu theo đúng version thư viện trong `package.json` (Context7 MCP), để spec và plan không dùng API cũ.
- Context7 đóng gói trong plugin, **tắt mặc định**, dự án bật bằng `integrations.docs.context7: true` (xem A6). Lúc implement phải kiểm tra lại cách cài và việc có cần API key không.

### A4. Tìm caller theo symbol — `/task:plan`, `/task:review`
- **Trạng thái:** đề xuất · **Đợt:** chưa xếp
- Dùng MCP dựa trên language server (vd Serena), vì grep không bắt được import bị đổi tên hay re-export. **Chỉ làm khi gặp lỗi sót caller thật.**

### A5. Template sản phẩm gửi đi — `/task:report`
- **Trạng thái:** xong · **Đợt:** 5 (đi cùng C4)
- **Template mặc định của plugin** (heading được dịch theo ngôn ngữ đích):

| Template | Dùng cho | Các phần |
|---|---|---|
| `comment.code` | Trả lời ticket sau khi fix | Tóm tắt (1–2 câu) · Nội dung đã sửa · Phạm vi ảnh hưởng · Cách kiểm tra · Việc còn lại / release |
| `comment.investigate` | Trả lời ticket điều tra | **Kết luận** (đặt đầu tiên) · Căn cứ (tóm tắt bằng lời) · Nguyên nhân · Đề xuất xử lý · Mục chưa xác nhận được (chỉ khi bị chặn bởi quyền hoặc quy định, ghi rõ lý do) |
| `report` | Báo cáo dài | Bối cảnh · Phạm vi · Phương pháp · Kết quả chi tiết · Kết luận · Đề xuất |
| `chat` | Tin Slack/Teams | 3–5 dòng: kết quả + việc cần người đọc làm |

- **Quy tắc cho mọi template:** chỉ ghi kết quả; không có path local, tên script hay phụ lục file; chỉ nêu điểm quan trọng, đúng scope ticket; không có giá trị secret (D5).
- **Dự án thay đổi được:**
  - Template riêng đặt ở `.claude/task-templates/<tên>.md`, được ưu tiên hơn template của plugin.
  - `output.markup`: `markdown` | `backlog` | `jira` | `textile`.
- **Slack:** MCP cần xác thực xong mới dùng được; trước đó chỉ ghi nháp ra file.

### A6. Cài đặt MCP
- **Trạng thái:** xong · **Đợt:** 2 (do `/task:init` thực hiện)

| MCP | Dùng ở | Cài ở đâu | Cách cài | Lý do |
|---|---|---|---|---|
| **Ticket** (Backlog / Jira / Redmine…) | A1 | **User scope** (`~/.claude.json`) | `/task:init` in sẵn lệnh `claude mcp add --scope user … <YOUR_API_KEY>`, **user tự chạy** và tự nhập key | Key là của từng người; AI không được nhìn thấy |
| **Playwright** | A2 | **Project scope ở workspace root** (`<workspace>/.mcp.json`) | `/task:init` tạo, pin version, tham số theo env | Phụ thuộc dự án; nằm ngoài git của repo sản phẩm |
| **Context7** | A3 | **Đóng gói trong plugin**, tắt mặc định | Plugin | Dùng chung; tắt vì phải gửi tên thư viện ra dịch vụ ngoài |
| **Slack, Claude Docs, Figma, Drive** | A5, đầu vào | Connector của claude.ai, theo từng user | User tự kết nối; `/task:init` chỉ kiểm tra | Plugin không cài được |

- **Quy tắc:**
  - **Pin version chính xác**, không dùng `@latest` (rủi ro supply chain). Nâng version là một thay đổi có chủ đích và được review.
  - **Output của mọi MCP đều đi qua G0b**, không có ngoại lệ.
  - **AI không nhập và không đọc credential của MCP.** `~/.claude.json` nằm trong `secret_paths` mặc định.
  - `/task:init` kiểm tra bằng `claude mcp list` và gọi thử một tool chỉ đọc. Thiếu MCP nào thì báo MCP đó, không chặn toàn bộ workflow.
- **Không dùng:** GitHub MCP (`gh` CLI đã đủ); Filesystem/Git MCP (Claude Code đã có sẵn); AWS MCP (dự án đã có skill đọc log riêng).

---

## B — Verify và các lỗi nhỏ

### B1. Lệnh verify
- **Trạng thái:** xong · **Đợt:** 2
- **Vấn đề:** agent con bị chặn quyền chạy lệnh, nên self-check và test mà plan tạo ra **chưa bao giờ được chạy**.
- **Thiết kế:**
  - **Chạy ở main session.** Không cấp quyền chạy lệnh cho agent con; agent con chỉ sửa code.
  - **2 cấp:**
    - Theo dự án: `verify` trong config.
    - Theo item: plan có thêm trường `- **Verify:** <lệnh>`, ví dụ self-check do item đó tạo ra.
  - **Chạy lúc nào:**
    - `/task:implement`: sau mỗi nhóm item, chạy verify của các item đó và các lệnh có `when: implement`.
    - `/task:review`: chạy toàn bộ.
  - Output chạy qua `scan-run` (D4), lưu ở `evidence/verify-<tên>.log`. Model chỉ thấy pass/fail và phần lỗi.
  - **Fail ở implement:** item vẫn `done`, ghi lỗi vào item và báo user, không tự sửa lặp. **Fail ở review:** tính là blocker.
  - **Timeout:** mặc định 300 giây, đặt riêng được cho từng lệnh.
  - **Chưa khai báo verify:** không tự đoán lệnh. Review ghi "chưa có verify" và gợi ý `/task:init`.
  - Lệnh verify vẫn đi qua Security Gate như mọi lệnh khác.
- **Config:**
  ```yaml
  verify:
    - { name: lint,   run: "npx eslint {changed_files}",            when: [implement, review] }
    - { name: format, run: "npx prettier --check {changed_files}",  when: [review] }
    - { name: e2e,    run: "npx playwright test --grep @{task_id}", when: [review], timeout: 900 }
  ```
  Biến dùng được: `{repo}`, `{changed_files}` (file đã sửa so với base), `{task_id}`. Lệnh chạy với thư mục làm việc là `{repo}`.

### B2. Review làm inline thay vì spawn agent
- **Trạng thái:** xong · **Đợt:** 6
- **Vấn đề:** khi ít file, main session tự review thay vì spawn agent theo lane. Kết quả vẫn đúng nhưng lệch so với skill.
- **Đề xuất:** cho phép chính thức. Tổng số file ≤ 3 thì review inline; nhiều hơn thì spawn agent theo lane.

### B3. Ghi đè khi chạy non-interactive
- **Trạng thái:** xong · **Đợt:** 6
- **Vấn đề:** chạy bằng `claude -p` thì skill không hỏi được "Overwrite? (y/n)", nên phải dừng.
- **Đề xuất:** thêm tham số `--force` cho `/task:spec`, `/task:plan`, `/task:report`.

### B4. Task cũ chưa có `.repo`
- **Trạng thái:** xong · **Đợt:** 6
- **Vấn đề:** task cũ mặc định dùng `repos.default`. Nếu task thật ra làm trên repo khác thì review đọc nhầm repo.
- **Đề xuất:** khi thiếu `.repo`, đoán repo từ path trong `3_plan.md`, hỏi user xác nhận một lần rồi ghi `.repo`.

---

## C — Task điều tra

### Vấn đề
Task điều tra đang bị ép vào format của task code:
- Item trong plan có dạng "code trước/sau".
- Kết quả rải rác ở file tự đặt tên (`findings_Cx.md`, `aws-data/`…).
- Phải tự viết tay item tổng hợp root cause.
- Review kiểm "code có khớp spec không", trong khi cần kiểm "kết luận có bằng chứng không".
- Không có ràng buộc read-only, dù thường chạm vào production.
- Điều tra xong muốn fix thì phải tự tạo task mới và copy kết luận sang.

### C1. Loại task `investigate`
- **Trạng thái:** xong · **Đợt:** 3
- **Làm gì:** `/task:new <id> [repo] --type investigate`, ghi loại vào `.type` (mặc định `code`). Vẫn dùng các lệnh và 5 file hiện có; mỗi skill đọc `.type` để đổi hành vi:

| | `code` | `investigate` |
|---|---|---|
| `2_spec.md` | Vấn đề, giải pháp, scope, rủi ro | **Câu hỏi cần trả lời** · giả thuyết H1..Hn · nguồn dữ liệu (code, log, DB, AWS env) · tiêu chí để kết luận · env/profile được phép |
| `3_plan.md` | `[Cx]` code trước/sau | `[Qx]`: kiểm giả thuyết nào · lệnh/query cụ thể · **kỳ vọng nếu đúng và nếu sai** · env/profile · mức security (G2) · Deps |
| `/task:implement` | Sửa code | Chạy kiểm tra ở chế độ read-only (C2). Bằng chứng lưu `evidence/Qx-*`. Ghi vào item `Result: confirmed / rejected / inconclusive` kèm link bằng chứng |
| `4_review.md` | Logic, checklist, verify | **Kiểm bằng chứng:** kết luận nào thiếu evidence, giả thuyết nào chưa kiểm, kết quả nào mâu thuẫn, chỗ nào chỉ là suy luận |
| `5_report.md` | Thay đổi đã làm | **Câu trả lời** · root cause · **mức độ chắc chắn** · bảng bằng chứng · bước tiếp theo |

### C2. Chế độ read-only khi điều tra
- **Trạng thái:** xong · **Đợt:** 3
- **Phạm vi (sửa khi rà soát):** read-only chỉ áp dụng **khi đang chạy `/task:implement` của task `investigate`**. Lúc bắt đầu, skill tạo file đánh dấu `tasks/<id>/.readonly`; chạy xong thì xoá. Hook thấy file này thì áp dụng thêm các rule read-only. Ngoài lúc đó, các thao tác ghi như commit hay deploy vẫn chạy bình thường (và vẫn bị Security Gate kiểm tra phần secret).
  - Nếu skill dừng giữa chừng và file đánh dấu còn sót lại: hook nhắc user xoá. Hook không tự xoá.
- **Khi read-only bật:**
  - Agent chỉ được ghi file trong thư mục task.
  - Lệnh ghi hoặc deploy bị chặn: `aws * create-* / update-* / put-* / delete-*`, `lambda update-function-code`, `git commit / push / checkout / reset`, cùng các lệnh deploy do dự án khai báo trong `security.commands.deny`.
  - Lệnh đọc dữ liệu nghiệp vụ hoặc dữ liệu cá nhân (`dynamodb scan / query / get-item`, `cognito-idp list-users`, `s3 cp`, `curl`) và **lệnh chưa được phân loại** → hỏi user (mức confirm). Ở bước plan (G2), các lệnh này được gom lại để hỏi **một lần** trước khi chạy. Câu hỏi nêu rõ lệnh, env/profile và lý do.
  - Mọi lệnh AWS phải ghi `--profile` rõ ràng.
- Phần chặn secret (D2, D3) áp dụng **mọi lúc**, không phụ thuộc chế độ read-only.

### C3. Từ điều tra sang fix: `--from`
- **Trạng thái:** xong · **Đợt:** 4
- `/task:new <ticket>-fix --from <task-điều-tra>` tạo task `code` cho **cùng ticket**. `1_requirements.md` được điền sẵn câu trả lời, root cause và đề xuất fix từ `5_report.md` của task gốc, kèm link quay lại task gốc.
- **Lý do:** task 844 phải trộn điều tra và fix trong một plan.

### C4. Sản phẩm gửi đi theo nhiều ngôn ngữ
- **Trạng thái:** xong · **Đợt:** 5 (đi cùng A5)
- **Luồng:**
  1. `/task:report` viết `5_report.md` (nội bộ) và soạn sản phẩm theo template (A5) vào `output_<review_language>/<loại>/`.
  2. User duyệt và sửa bản này.
  3. `/task:report --final` dịch sang `output/<loại>/` theo `output.languages`, rồi đối chiếu để chắc 2 bản khớp nội dung.
- **Quy tắc:**
  - Chỉ sửa bản để duyệt. Bản trong `output/` luôn được tạo lại từ bản duyệt, không sửa tay.
  - Ngôn ngữ duyệt trùng ngôn ngữ gửi đi → ghi thẳng vào `output/`.

### C5. Cấu trúc folder task
- **Trạng thái:** xong · **Đợt:** 3
- Cấu trúc xem phần 1. Quy tắc:
  - `assets/` chỉ chứa đầu vào.
  - `evidence/`, `scripts/`, `output*/` chỉ tạo khi có nội dung.
  - `output*/` dành cho người khác đọc: chỉ ghi kết quả, không có path local hay tên script, phương pháp mô tả bằng lời.
  - `5_report.md` là bản nội bộ, được trỏ tới `evidence/` và `scripts/`.
  - Task code dùng cùng cấu trúc, thường chỉ có `evidence/`.

### Không làm lúc này
- **Loại task `doc`** (review tài liệu): mới gặp một lần, chưa đủ để thiết kế.
- **Trộn `[Cx]` và `[Qx]` trong cùng một plan:** dùng C3 để nối 2 task thì đơn giản hơn.

---

## D — Security Gate: secret không được lên AI cloud

### D1. Nguyên tắc
- Mọi thứ đi vào context của model đều được gửi lên cloud: output lệnh, file đã đọc, kết quả MCP, kết quả agent con, cả câu user gõ vào. **Secret phải bị chặn trước khi xuất hiện trong output của tool.** User xác nhận cũng không thay đổi được điều này.
- **Secret** gồm: access key, secret key, token, password, API key, private key, connection string, và giá trị của biến môi trường hay parameter chứa những thứ đó.
- **Lớp chặn chính là hook** do harness thực thi. Lời dặn trong skill chỉ là lớp phụ.
- Áp dụng **mọi lúc, mọi loại task**, kể cả khi không có task nào active.
- **Plugin tự bảo vệ, không dựa vào memory của user.** Người khác cài plugin được bảo vệ ngay mà không cần cấu hình.

### D0. Cấu trúc module
- **Trạng thái:** xong · **Đợt:** 1
```
security/
├── policy.default.yml   ← path secret, pattern secret, phân loại lệnh
├── gate.py              ← hook PreToolUse / PostToolUse + CLI `scan-run`, `scan <file>`
└── test_gate.py         ← self-check: secret giả, lệnh vi phạm, path cấm → tất cả phải bị chặn hoặc niêm phong
hooks/hooks.json         ← đăng ký gate, chạy mọi lúc
```

**Policy gồm 2 lớp:**
- **Mặc định của plugin:** luôn áp dụng.
- **Bổ sung của dự án** (`security:` trong config) — **chỉ được siết thêm:**
  - Thêm `secret_paths`, `secret_patterns`.
  - Thêm lệnh vào `deny` hoặc `confirm`.
  - Thêm lệnh vào `allow` **chỉ khi** lệnh đó chưa được policy mặc định phân loại. Không thể đưa một lệnh đang bị deny, safe-form hay confirm xuống allow.
  ```yaml
  security:
    secret_paths: ["e2e/.auth/**"]
    commands:
      allow:   ["amplify status", "amplify env list"]
      confirm: ["amplify pull *", "amplify env checkout *"]
      deny:    ["amplify push *", "amplify publish *"]   # chỉ áp dụng khi read-only (C2)
  ```

**Các điểm gate:**

| Điểm | Ở đâu | Kiểm tra | Vi phạm thì |
|---|---|---|---|
| **G0** | Mọi tool call, mọi lúc (cả agent con) | PreToolUse: path secret, lệnh lộ secret, dạng an toàn (D2, D3); rule read-only nếu có `.readonly` (C2) | Chặn kèm gợi ý cách an toàn; lệnh mức confirm → hook trả `ask` để user quyết |
| **G0b** | Output của **mọi** MCP tool | PostToolUse quét pattern (D4) | Thay output bằng thông báo niêm phong (`updatedMCPToolOutput`); bản gốc lưu `evidence/.sealed/` nếu có task active, nếu không thì bỏ |
| **G1** | `/task:new` | File đính kèm tải về được quét bằng `scan` trước khi ai đọc | Chuyển file vào `evidence/.sealed/`, báo user |
| **G2** | `/task:plan` | Mỗi lệnh trong plan được ghi mức theo policy; gom các lệnh confirm | Lệnh bị chặn hoặc sai dạng an toàn → viết lại plan trước khi chạy |
| **G3** | `/task:implement` | Lệnh có output khó đoán (log, `git log -p`, verify) chạy qua `scan-run` | Niêm phong vào `evidence/.sealed/` |
| **G4** | `/task:review` | Quét **diff code** (secret bị hardcode) và quét `evidence/` | Secret trong diff → **blocker** |
| **G5** | `/task:report --final` | Quét `output*/` và `5_report.md` | Không cho tạo bản cuối cho tới khi sạch |

**Nhật ký:** mọi lần chặn, niêm phong, hỏi xác nhận đều được ghi lại. Chỉ ghi loại sự kiện, lệnh hoặc path và rule bị vi phạm, **không ghi giá trị**.
- Có task active → ghi vào `tasks/<id>/.security.log`.
- Không có task active → ghi vào `~/.claude/task-security.log`.

**Khi gate lỗi (sửa khi rà soát):**
- `gate.py` tự bắt mọi lỗi bên trong và trả `deny` → **fail-closed**.
- **Ngoại lệ không tránh được:** nếu `python3` không có trên máy, hook lỗi trước khi chạy được dòng nào. Claude Code coi exit code khác 2 là lỗi không chặn, nên lúc đó tool call vẫn chạy (**fail-open**). Biện pháp:
  - `/task:init` và README yêu cầu có `python3`.
  - Mỗi skill `/task:*` kiểm tra lại ở bước đầu tiên; thiếu thì dừng.
- **Lối thoát khẩn cấp:** user tự đặt `TASK_SECURITY_GATE=off` khi khởi động Claude Code. Hook chặn mọi lệnh do model chạy mà có chứa chuỗi này.

**Đã kiểm chứng (2026-10-31, Claude Code 2.1.311), với hook khai báo trong settings của project:**
- PreToolUse chạy cho cả agent con (input có `agent_id`, `agent_type`). `deny` chặn được Read file secret bên trong Explore và general-purpose; nội dung không lọt vào phiên.
- PostToolUse dùng `updatedMCPToolOutput` thay được output của MCP trước khi model nhận; key giả không lọt vào phiên.
- **Còn phải test lúc implement:** cùng các kịch bản trên nhưng với hook khai báo trong `hooks/hooks.json` của plugin.

**Kiểm thử bắt buộc:** `python3 security/test_gate.py` phải pass trước mỗi lần commit plugin. Ghi quy định này trong phần contributing của README.

### D2. Chặn nguồn secret (G0)
- **Trạng thái:** xong · **Đợt:** 1
- **Path secret mặc định**, chặn với Read, Grep, Glob, Edit, Write, và với `cat` / `head` / `tail` / `grep` / `sed` / `less` / `cp` trong Bash:
  - File môi trường và key: `**/.env*`, `**/*.pem`, `**/*.key`, `**/*.p12`, `**/*.pfx`, `**/id_rsa*`, `**/id_ed25519*`
  - Credential của các công cụ: `**/*credentials*`, `**/.npmrc`, `**/.netrc`, `**/.git-credentials`, `~/.aws/**`, `~/.ssh/**`, `~/.config/gh/hosts.yml`
  - Credential của Claude và MCP: `~/.claude.json`
  - Output đã niêm phong: `**/evidence/.sealed/**`
  - **Ngoại lệ:** file mẫu như `*.example`, `*.sample`, `*.template` (vd `.env.example`) vẫn được đọc.
- **Lệnh in ra secret, luôn chặn:**
  - `env`, `printenv`, `set` (không tham số), `export -p`
  - `aws configure get aws_secret_access_key`, `aws configure export-credentials`
  - `secretsmanager get-secret-value`, `ssm … --with-decryption`, `lambda get-function` (trả URL tải code đã ký sẵn)
- **Lệnh chỉ chạy ở dạng an toàn (safe-form):** xem D3. Chạy dạng gốc → bị chặn, kèm gợi ý dạng an toàn.
- **Viết bằng python**, vì parse lệnh shell bằng shell rất dễ sai, và sai ở đây nghĩa là lọt secret. Lệnh không parse được → chặn.

### D3. Dạng an toàn cho các lệnh hay dùng
- **Trạng thái:** xong · **Đợt:** 1

| Cần gì | Không chạy | Dạng an toàn |
|---|---|---|
| Lambda có những biến môi trường nào | `get-function-configuration` (in cả value) | `--query '{Runtime:Runtime,Handler:Handler,Timeout:Timeout,MemorySize:MemorySize,EnvKeys:keys(Environment.Variables)}'` |
| API key của AppSync còn hạn không | `list-api-keys` (field `id` **chính là** API key) | `--query 'apiKeys[].{expires:expires,description:description}'` |
| Parameter có tồn tại, sửa lần cuối khi nào | `get-parameter --with-decryption` | `describe-parameters`, hoặc `get-parameter --query 'Parameter.{Name:Name,Type:Type,Version:Version,LastModifiedDate:LastModifiedDate}'` |
| Giá trị có giống nhau giữa 2 env không | In cả 2 giá trị ra rồi so | So ở local, chỉ in `same` / `different` (hoặc 8 ký tự đầu của sha256) |
| Code Lambda đã deploy | `get-function` | Đọc code trong repo; cần bản đã deploy thì tải về local mà không in URL |
| Lịch sử thay đổi | `git show <sha>`, `git log -p` trên toàn repo | `git log -p -- <path cụ thể>`, chạy qua `scan-run` |

### D4. Bộ quét (`scan-run`, `scan`)
- **Trạng thái:** xong · **Đợt:** 1
- **Dùng cho:** output khó đoán (log CloudWatch, `git log -p`, verify), file đính kèm, output của MCP (G0b) và file trong `output*/`.
- **Cách chạy:**
  1. Ghi output ra file.
  2. Quét pattern: `AKIA…`, `ASIA…`, `da2-…`, JWT `eyJ…`, `-----BEGIN … PRIVATE KEY`, `password=`, `secret=`, `token=`, `Authorization:`, chuỗi entropy cao. Dự án thêm pattern bằng `secret_patterns`.
  3. **Sạch** → in ra. **Có match** → không in gì; chuyển vào `evidence/.sealed/` và chỉ báo "N chuỗi giống secret, đã niêm phong".
- **Giới hạn (ghi trong README):** quét theo pattern có thể sót secret có format lạ, vd password dạng chữ thường. Vì vậy D2 (chặn từ nguồn) mới là lớp chính.
- **Bắt buộc có self-check.** Đưa vào secret giả và chắc chắn script không in nó ra. Đã từng có sự cố sed fail im lặng làm lộ secret.

### D5. Output gửi đi (G4, G5)
- Không trích nguyên văn giá trị cấu hình vào `output*/`. Chỉ ghi kết luận, ví dụ "key ở env A và env B khác nhau".
- `/task:review` và `/task:report --final` quét `output*/` và `5_report.md`. Còn match thì không được báo xong.

---

## Thứ tự implement

| Đợt | Mục | Lý do |
|---|---|---|
| **1** | D0 + D2 + D3 + D4 + D5 (Security Gate) | Mọi tích hợp sau đều đưa thêm dữ liệu bên ngoài vào context, nên phải có lớp chặn trước |
| **2** | A0 + A6 + A1 + B1 | Lợi nhiều nhất. A0 tạo config và cài MCP mà A1, B1 cần |
| **3** | C5 + C1 + C2 | Task điều tra; C5 là nền, C2 bảo đảm an toàn |
| **4** | A2 + C3 | A2 dùng hạ tầng verify của B1 |
| **5** | A5 + C4 + A3 | Sản phẩm gửi đi, tra tài liệu |
| **6** | B2 + B3 + B4 | Sửa nhỏ, gộp một lần |
| — | A4 | Chỉ làm khi có lý do cụ thể |

Mỗi đợt kết thúc bằng: test trong sandbox (như cách đã test v0.1) → cập nhật README → commit → user xác nhận rồi mới sang đợt sau.
