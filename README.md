🚗 VinFast Smart Integration cho Home Assistant

Tích hợp (Integration) siêu việt đưa chiếc ô tô điện VinFast của bạn vào hệ sinh thái Home Assistant. 
Không chỉ đơn thuần là kéo thông số, Component này được trang bị các thuật toán Khoa học Dữ liệu (Data Science) đỉnh cao để biến Home Assistant thành một "Trung tâm phân tích viễn trắc" (Telemetry Hub) mạnh mẽ, hoạt động 24/7 mà không cần mở App điện thoại.

✨ Các tính năng cốt lõi (Core Features)

🚀 Dữ liệu Thời gian thực (Real-time MQTT): 

Sử dụng kết nối WebSockets trực tiếp tới AWS IoT Core của VinFast với cơ chế tự động vượt rào (Bypass) để duy trì luồng dữ liệu 24/7. Tự động trả lời ping từ T-Box của xe.

🧠 Phân tích Động học Lượng tử (Smart Profiling): 

Thuật toán đếm tần suất mẫu tốc độ (Frequency Sampling) thông minh. Tự động loại bỏ nhiễu do dừng đèn đỏ và phân tích chính xác "Dải tốc độ tối ưu nhất" mỗi khi pin sụt 1%.

🔋 Quản lý Sạc Tức thời (Smart Charging): 

Bắt sự kiện Cắm/Rút súng sạc trong vài giây thông qua MQTT. Tự động tạo luồng ngầm để lấy hóa đơn sạc (Số kWh, Hiệu suất) từ máy chủ sau khi chốt phiên sạc.

⏱️ Quản lý Chuyến đi: 

Tự động nhận diện chuyến đi mới khi bánh xe lăn. Chốt sổ chuyến đi (Quãng đường, Chi phí điện/xăng quy đổi, Vận tốc trung bình) nếu xe đỗ tĩnh quá 30 phút.

🗺️ GPS Tĩnh tâm (Anti-flicker Tracking): 

Thuật toán làm tròn sai số vệ tinh (11 mét) để tọa độ device_tracker không bị nhảy loạn xạ khi xe đang đỗ tĩnh trong gara, giúp tiết kiệm tài nguyên cho Home Assistant.

🎮 Điều khiển Từ xa Động (Dynamic Remote): 

Tích hợp các nút bấm Mở khóa, Bật điều hòa, Tìm xe... Cấu trúc Entity ID được chuẩn hóa dạng [model]_[vin] giúp quản lý nhiều xe cùng lúc không bị xung đột.

📥 Hướng dẫn Cài đặt qua HACS (Khuyên dùng)

Cách dễ nhất để cài đặt và nhận các bản cập nhật tự động là sử dụng HACS (Home Assistant Community Store).

1) Mở Home Assistant, truy cập vào menu HACS ở cột bên trái.

2) Chọn mục Integrations (Tích hợp).

3) Bấm vào biểu tượng 3 chấm ở góc trên cùng bên phải, chọn Custom repositories (Kho lưu trữ tùy chỉnh).

4) Điền các thông tin sau:

Repository: [https://github.com/thangnd85/vinfast-connected-car]

Category: Chọn Integration.

5) Bấm Add (Thêm).

Đóng hộp thoại, lúc này bạn sẽ thấy Tích hợp "VinFast" xuất hiện trên màn hình HACS. Bấm vào nó và chọn Download (Tải về).

⚠️ Quan trọng: Khởi động lại Home Assistant của bạn.

⚙️ Cấu hình Tích hợp (Configuration)
Sau khi cài đặt và khởi động lại, bạn tiến hành đăng nhập vào xe:

1) Vào Cài đặt (Settings) -> Thiết bị & Dịch vụ (Devices & Services).

2) Bấm nút Thêm tích hợp (Add Integration) ở góc dưới bên phải.

3) Gõ VinFast vào ô tìm kiếm và chọn nó.

4) Nhập Email và Mật khẩu tài khoản App VinFast của bạn. (Chỉ lưu trong Home Assistant, không gửi đến nơi nào khác)

Home Assistant sẽ tự động quét, lấy mã VIN và sinh ra toàn bộ Cảm biến (Sensor) & Nút bấm (Button) với cấu trúc chuẩn:

sensor.[model]_[vin]_[tên_cảm_biến] (VD: sensor.vf8_abcd1234_phan_tram_pin).

🛠️ Cấu hình Tùy chọn nâng cao (Options)
Tích hợp này cho phép bạn tính toán chi phí sạc và so sánh với xe xăng theo thời gian thực.
Tại màn hình Quản lý Tích hợp VinFast, bấm vào nút Cấu hình (Configure) để thay đổi:

- Giá điện: Mặc định 4000 VNĐ/kWh.

- Giá xăng quy đổi: Mặc định 20.000 VNĐ/Lít.

- Mức tiêu thụ Điện tham chiếu (kWh/km).

- Mức tiêu thụ Xăng tham chiếu (km/Lít).

🎨 Giao diện điều khiển (Frontend / Dashboard)
Kho lưu trữ này chỉ chứa mã nguồn Backend (Core Component) sinh ra các thực thể.
Để có giao diện Digital Twin mô phỏng xe 3D và các bảng thống kê xịn xò, vui lòng truy cập và cài đặt Custom Card tại kho lưu trữ Frontend của chúng tôi:

👉 [https://github.com/thangnd85/vinfast-digital-twin-card]

🛡️ Tuyên bố Miễn trừ trách nhiệm (Disclaimer)

Dự án này được phát triển bởi cộng đồng Open Source và KHÔNG phải là sản phẩm, cũng như không được chứng nhận hay liên kết chính thức với VinFast Auto.

Mọi hành động tương tác, lấy dữ liệu và ra lệnh điều khiển từ xa (Mở khóa, Bật AC...) đều gọi qua API nội bộ của Ứng dụng di động VinFast. Người dùng hoàn toàn tự chịu trách nhiệm về mọi rủi ro (nếu có) đối với phương tiện của mình khi sử dụng tích hợp này.

Mã nguồn cam kết không lưu trữ bất kỳ thông tin cá nhân hay mật khẩu nào ngoài phạm vi của bộ nhớ Home Assistant cục bộ của bạn.


Để có giao diện đẹp, đọc thêm:

[https://github.com/thangnd85/vinfast-digital-twin-card]

<img width="484"  alt="image" src="https://github.com/user-attachments/assets/cd5410a9-936f-459e-ba8f-a7628413b85c" />

<img width="484" alt="image" src="https://github.com/user-attachments/assets/ca1d18dc-8d4d-46f9-a87e-57c492bffb17" />

<img width="484" alt="image" src="https://github.com/user-attachments/assets/fd32dc0c-70e1-4619-977c-49c19a3a2424" />

<img width="484" alt="image" src="https://github.com/user-attachments/assets/11f68c2d-4bdc-4003-8bdf-63b0e54c0600" />

<img width="484"  alt="image" src="https://github.com/user-attachments/assets/a2f4a13a-4609-4833-9838-a163d9ff4b3f" />

