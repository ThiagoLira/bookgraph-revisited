CUDA_VISIBLE_DEVICES=0 llama-server -m /home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf -c 40000 -np 30 --repeat-penalty 1.2 \
  --batch-size 1  \
  -fa on \
  --repeat-last-n 128 \
  --presence-penalty 0.4 \
  --frequency-penalty 0.6 \
   --n-gpu-layers -1 \
