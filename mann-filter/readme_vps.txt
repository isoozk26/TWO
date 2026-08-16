nohup uvicorn ikiler_mahle_fiyat_stok_fast_api_n8n:app --host 0.0.0.0 --port 8888 > nohup.out 2>&1 &


lsof -i :8888


kill -9 <PID>

fuser -k 8888/tcp



/sync/mahle/start   → MAHLE
/sync/mann/start    → MANN-FILTER
/sync/purflux/start → PURFLUX
/sync/ufi/start     → UFI FILTERS
/sync/filtorq/start → FILTORQ
/sync/filtron/start → FILTRON
/sync/all/start     → HEPSİ


curl http://45.87.120.230:8888/health





cd /home/fast-api/ikiler
source venv/bin/activate
nohup python -m uvicorn ikiler_mahle_fiyat_stok_fast_api_n8n:app --host 0.0.0.0 --port 8888 > nohup.out 2>&1 &
sleep 3
cat nohup.out
ss -tulpn | grep 8888
