python3 generate_moves.py > input.txt

python3 generate_lm.py --input_txt input.txt --output_dir . \
  --top_k 500000 --kenlm_bins ./kenlm/build/bin/ \
  --arpa_order 5 --max_arpa_memory "85%" --arpa_prune "0|0|1" \
  --binary_a_bits 255 --binary_q_bits 8 --binary_type trie --discount_fallback

./generate_scorer_package --alphabet ../alphabet.txt --lm lm.binary --vocab vocab-500000.txt \
  --package ../chess.scorer --default_alpha 0.931289039105002 --default_beta 1.1834137581510284
