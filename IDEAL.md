tạo một hệ thống mới tên là Mèo Bot:
Phần cứng:
- ESP-12F — vi điều khiển WiFi, mic, loa, OLED, DHT
- NodeMCU — board cắm ESP-12F, USB, 3V3/5V
- SSD1306 — OLED 0.96" I2C (module JMD0.96D-1)
- INMP441 — mic I2S
- MAX98357 — amp I2S
- Loa 3W — phát TTS/SFX
- DHT11 — nhiệt độ / độ ẩm
Backend: máy tính này
Tôi muốn có các chức năng:
- Nghe và phản hồi
- 1 trang web để tôi monitor, lưu ý là không tăng tải của thiết bị phần cứng
Yêu cầu:
- có thể phản hồi tự nhiêu và nhanh
- dùng local ollama để phản hồi:
+ tôi muốn sẽ khởi tạo 1 phiên trước ở backend để dùng lại, bắt đầu bằng prompt như sau: "bạn là một chatbot mini, luôn trả lời ngắn gọn và dễ thương. chỉ trả lời thôi không phải giải thích gì thêm. Không trả lời bằng emoji, chỉ dùng chữ"
+ backend phải xử lý được mượt mà, can nhắc dung python hoặc c++, kiểm tra kỹ khả năng trước khi bắt đầu
- có một dự án gần tương tự là xiaozhi AI nhưng cần phải dùng dịch vụ ngoài, hãy tham khảo tính năng, kỹ thuật của dự án này

Ngoài ra tôi có để lại file .env để tham khảo từ dự án trước

