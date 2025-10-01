# 🎬 SRT Glossary Tool Pro

> **Công cụ xử lý phụ đề SRT thông minh với giao diện đồ họa**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-orange.svg)](https://docs.python.org/3/library/tkinter.html)

## 📋 Mô tả

**SRT Glossary Tool Pro** là một ứng dụng desktop được thiết kế để xử lý hàng loạt file phụ đề SRT (.srt) với khả năng thay thế từ/cụm từ theo quy tắc tùy chỉnh. Ứng dụng sử dụng giao diện đồ họa thân thiện với người dùng và hỗ trợ quản lý backup an toàn.

## ✨ Tính năng chính

### 🔄 **Xử lý phụ đề hàng loạt**

- Xử lý nhiều file SRT cùng lúc
- Hỗ trợ đệ quy (xử lý cả subfolder)
- Tự động phát hiện encoding (UTF-8, UTF-16, CP1258)
- Chế độ Dry-run để xem trước thay đổi

### 📚 **Quản lý Glossary thông minh**

- Tạo và quản lý quy tắc thay thế bằng Regex
- Hỗ trợ tiếng Việt có dấu/không dấu
- Import/Export glossary từ file JSON
- Bật/tắt quy tắc linh hoạt
- Sắp xếp thứ tự ưu tiên quy tắc

### 🛡️ **Backup & Khôi phục**

- Tự động tạo backup (.bak) trước khi chỉnh sửa
- **Revert từ backup** - Khôi phục file gốc từ .bak
- **Xóa backup files** - Dọn dẹp file backup không cần thiết
- Quản lý backup an toàn với xác nhận

### 📊 **Lịch sử & Theo dõi**

- Lưu lịch sử tất cả lần chạy
- Xem chi tiết log từng lần xử lý
- Thống kê số file đã xử lý/thay đổi
- Database SQLite để lưu trữ lịch sử

## 🚀 Cài đặt & Sử dụng

### Yêu cầu hệ thống

- Python 3.7 trở lên
- Thư viện: `tkinter` (có sẵn với Python)

### Cài đặt

```bash
# Clone repository
git clone https://github.com/vukiman1/ChangeSubtitleScript.git
cd ChangeSubtitleScript

# Chạy ứng dụng
python srt_tool_pro.py
```

## 🎯 Hướng dẫn sử dụng

### 1. **Tab Run - Xử lý file**

- **Chọn folder**: Browse hoặc dán đường dẫn folder chứa file .srt
- **Tùy chọn**:
  - ☑️ **Đệ quy**: Xử lý cả subfolder
  - ☑️ **Dry-run**: Chỉ xem trước, không ghi file
  - ☑️ **Tạo backup**: Tự động backup trước khi sửa
- **Quản lý backup**:
  - 🔄 **Revert từ .bak**: Khôi phục file gốc từ backup
  - 🗑️ **Xóa .bak files**: Dọn dẹp file backup

### 2. **Tab Glossary - Quản lý quy tắc**

- ➕ **Thêm rule**: Tạo quy tắc thay thế mới
- ✏️ **Sửa rule**: Chỉnh sửa quy tắc đã có
- 🗑️ **Xóa rule**: Xóa quy tắc không cần
- 🔄 **Bật/Tắt**: Kích hoạt/vô hiệu hóa quy tắc
- ⬆️⬇️ **Sắp xếp**: Thay đổi thứ tự ưu tiên
- 📥📤 **Import/Export**: Sao lưu và chia sẻ glossary

### 3. **Tab History - Xem lịch sử**

- 📋 Danh sách tất cả lần chạy
- 📄 Xem chi tiết log từng lần
- 📊 Thống kê hiệu suất

### 4. **Tab Settings - Cấu hình**

- 📁 Đường dẫn file cấu hình
- 💡 Gợi ý regex cho tiếng Việt

## 📝 Ví dụ quy tắc Glossary

### Thay thế từ tiếng Việt

```regex
# Hình ảnh -> Image
(?i)(?<![A-Za-zÀ-ỹ])hình\s*ảnh(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])hinh\s*anh(?![A-Za-zÀ-ỹ])

# Nút -> Node
(?i)(?<![A-Za-zÀ-ỹ])nút(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])nut(?![A-Za-zÀ-ỹ])

# Thùng chứa -> Container
(?i)(?<![A-Za-zÀ-ỹ])thùng\s*chứa(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])thung\s*chua(?![A-Za-zÀ-ỹ])
```

### Mẹo Regex tiếng Việt

- Sử dụng `(?<![A-Za-zÀ-ỹ]) ... (?![A-Za-zÀ-ỹ])` để match nguyên từ
- `(?i)` để không phân biệt hoa thường
- `\s*` để bỏ qua khoảng trắng
- `|` để kết hợp nhiều pattern

## 📁 Cấu trúc file

```
srtScript/
├── srt_tool_pro.py      # Ứng dụng chính
├── glossary.json        # File glossary (tự tạo)
├── history.db          # Database lịch sử (tự tạo)
├── config.json         # File cấu hình (tự tạo)
└── readme.md           # Hướng dẫn này
```

## 🔧 Tính năng nâng cao

### Backup Management

- **Tự động backup**: Mỗi file .srt được backup thành .bak trước khi sửa
- **Revert an toàn**: Khôi phục file gốc từ backup với xác nhận
- **Cleanup**: Xóa hàng loạt file backup không cần thiết

### Error Handling

- Xử lý lỗi encoding tự động
- Báo cáo chi tiết lỗi xử lý
- Tiếp tục xử lý khi gặp lỗi file đơn lẻ

### Performance

- Xử lý đa luồng không block UI
- Progress bar theo dõi tiến độ
- Hỗ trợ dừng giữa chừng

## 🤝 Đóng góp

Mọi đóng góp đều được chào đón! Hãy tạo issue hoặc pull request.

## 📄 License

Dự án này được phân phối dưới giấy phép MIT. Xem file `LICENSE` để biết thêm chi tiết.

## 👨‍💻 Tác giả

**vukiman1** - [GitHub](https://github.com/vukiman1)

---

⭐ **Nếu thấy hữu ích, hãy star repo này!** ⭐
