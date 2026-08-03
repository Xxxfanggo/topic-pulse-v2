# 启动后端服务命令
```shell
#项目根目录topic-pulse-v2下运行：
python -m uvicorn topic_pulse_v2_chat.web:app --host 127.0.0.1 --port 8000 --reload
```

# 启动前端服务命令
```shell
#项目根目录src/topic_pulse_v2_chat/web/frontend下运行：
npm install
npm run dev
```