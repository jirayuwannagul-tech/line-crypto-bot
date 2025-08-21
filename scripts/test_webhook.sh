#!/bin/bash
# script สำหรับทดสอบ LINE Webhook

curl -X POST http://127.0.0.1:8000/line/webhook \
  -H "Content-Type: application/json" \
  -H "x-line-signature: dummy" \
  -d '{
    "events": [
      {
        "type": "message",
        "replyToken": "dummy-token",
        "source": {
          "userId": "U1234567890",
          "type": "user"
        },
        "timestamp": 1730000000000,
        "mode": "active",
        "message": {
          "id": "1234567890123",
          "type": "text",
          "text": "วิเคราะห์ btc"
        }
      }
    ]
  }'

