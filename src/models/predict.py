"""
Skrip inferensi Masked Language Model untuk Mini-BERT Bahasa Indonesia dari nol.
Dapat dijalankan melalui CLI:
    python -m src.models.predict --text "Ibu kota Indonesia adalah [MASK]."
"""

import argparse
import sys
from typing import Any, Dict, List, Optional

import torch

from src.data.tokenizer import WordLevelTokenizer, SPECIAL_TOKEN_IDS
from src.models.bert import MiniBertForMaskedLM


def predict_mask(
    text: str,
    checkpoint_dir: str,
    tokenizer_dir: str,
    top_k: int = 5,
    device: str = "auto",
) -> Dict[str, Any]:
    """
    Fungsi inferensi untuk memprediksi token pada posisi [MASK].

    Argumen:
        text: Kalimat input bahasa Indonesia yang memuat satu atau lebih token [MASK].
        checkpoint_dir: Direktori tempat model.pt dan config.json tersimpan.
        tokenizer_dir: Direktori tempat vocab.json dan tokenizer_config.json tersimpan.
        top_k: Jumlah kandidat token biasa teratas yang ditampilkan (integer positif).
        device: 'cpu', 'cuda', atau 'auto'.

    Kembalian:
        Kamus hasil inferensi lengkap dengan token terprediksi, probabilitas, dan metadata.
    """
    # 1. Validasi teks awal
    if not isinstance(text, str) or len(text.strip()) == 0:
        raise ValueError("Input teks tidak boleh kosong atau hanya berupa spasi.")

    # 2. Validasi top-k
    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError(f"top_k harus berupa integer positif (> 0), diperoleh: {top_k}.")

    # 3. Penentuan device dengan penolakan eksplisit jika CUDA diminta tetapi tidak ada
    dev_str = device.lower().strip()
    if dev_str == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("Perangkat CUDA diminta melalui device='cuda', namun torch.cuda.is_available() bernilai False.")
        selected_device = torch.device("cuda:0")
    elif dev_str == "cpu":
        selected_device = torch.device("cpu")
    elif dev_str == "auto":
        selected_device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    else:
        raise ValueError(f"Opsi device '{device}' tidak dikenal. Pilih 'cpu', 'cuda', atau 'auto'.")

    # 4. Pemuatan tokenizer dan model dengan validasi integritas
    tokenizer = WordLevelTokenizer.from_pretrained(tokenizer_dir)
    model = MiniBertForMaskedLM.from_pretrained(
        checkpoint_dir,
        filename="model.pt",
        tokenizer_dir=tokenizer_dir,
        require_tokenizer=True,
    )
    model.to(selected_device)
    model.eval()

    # 5. Tokenisasi teks input
    raw_tokens = tokenizer.tokenize(text)
    if len(raw_tokens) == 0:
        raise ValueError("Input teks menghasilkan 0 token setelah normalisasi dan pembersihan.")

    # 6. Temukan token [MASK] sebelum penambahan token khusus dan pembatasan panjang
    mask_token_str = tokenizer.mask_token
    mask_indices_in_content = [
        idx for idx, tok in enumerate(raw_tokens)
        if tok == mask_token_str
    ]

    if len(mask_indices_in_content) == 0:
        raise ValueError(
            f"Input teks tidak memuat token {mask_token_str}. "
            f"Fungsi inferensi ini mewajibkan minimal satu token {mask_token_str} pada kalimat masukan."
        )

    # 7. Penolakan input yang melebihi kapasitas maksimum (tanpa pemotongan diam-diam)
    # Total panjang urutan adalah panjang token isi ditambah 1 token [CLS] dan 1 token [SEP]
    total_seq_len = len(raw_tokens) + 2
    if total_seq_len > model.config.max_position_embeddings:
        raise ValueError(
            f"Panjang urutan masukan ({total_seq_len} token termasuk [CLS] dan [SEP]) melebihi batas "
            f"kapasitas maksimum model ({model.config.max_position_embeddings} token). "
            f"Masukan ditolak untuk mencegah pemotongan konteks atau token {mask_token_str} secara sepihak."
        )

    # 8. Susun token urutan penuh dengan [CLS] di awal dan [SEP] di akhir
    seq_tokens = [tokenizer.cls_token] + raw_tokens + [tokenizer.sep_token]
    input_ids_list = tokenizer.convert_tokens_to_ids(seq_tokens)
    attention_mask_list = [1] * len(input_ids_list)

    # Indeks token [MASK] pada urutan penuh bergeser +1 karena token [CLS] di indeks 0
    mask_positions = [idx + 1 for idx in mask_indices_in_content]

    # 9. Analisis token yang menjadi [UNK] untuk transparansi keterbatasan vocabulary
    unk_token_id = tokenizer.unk_token_id
    unk_words = [
        tok for tok, tid in zip(seq_tokens, input_ids_list)
        if tid == unk_token_id and tok not in SPECIAL_TOKEN_IDS
    ]

    # Batasi top_k terhadap jumlah token reguler yang tersedia
    num_regular_tokens = model.config.vocab_size - len(SPECIAL_TOKEN_IDS)
    effective_top_k = min(top_k, num_regular_tokens)

    # 10. Inferensi model menggunakan inference_mode
    with torch.inference_mode():
        input_ids_tensor = torch.tensor([input_ids_list], dtype=torch.long, device=selected_device)
        attention_mask_tensor = torch.tensor([attention_mask_list], dtype=torch.long, device=selected_device)

        logits = model(input_ids=input_ids_tensor, attention_mask=attention_mask_tensor)
        # Probabilitas dihitung melalui softmax atas seluruh vocabulary (8.000 token)
        full_probs = torch.softmax(logits, dim=-1)

    # 11. Ekstraksi prediksi untuk setiap posisi [MASK]
    predictions_per_mask: List[Dict[str, Any]] = []

    for mask_pos in mask_positions:
        pos_probs = full_probs[0, mask_pos].clone()

        # Kecualikan seluruh token khusus (ID 0..4) dari pemeringkatan
        for special_id in SPECIAL_TOKEN_IDS.values():
            pos_probs[special_id] = -1.0

        top_probs, top_ids = torch.topk(pos_probs, k=effective_top_k)

        candidates = []
        for rank, (score, tid) in enumerate(zip(top_probs.tolist(), top_ids.tolist()), start=1):
            token_str = tokenizer.convert_ids_to_tokens([tid])[0]
            candidates.append({
                "rank": rank,
                "token": token_str,
                "token_id": tid,
                "probability": score,
            })

        predictions_per_mask.append({
            "sequence_position": mask_pos,
            "candidates": candidates,
        })

    # 11. Ekstraksi status pelatihan checkpoint
    checkpoint_status = getattr(model, "checkpoint_status", "unknown")
    if not isinstance(checkpoint_status, str) or not checkpoint_status.strip():
        checkpoint_status = "unknown"
    else:
        checkpoint_status = checkpoint_status.strip()

    if checkpoint_status == "random_init":
        status_message = (
            "Status Checkpoint: random_init (Bobot inisialisasi acak, belum dilatih. "
            "Hasil prediksi ini murni merupakan smoke test untuk memverifikasi saluran inferensi, "
            "bukan representasi pemahaman bahasa atau akurasi prediksi)."
        )
    elif checkpoint_status == "trained":
        status_message = "Status Checkpoint: trained (Model telah melalui proses pelatihan)."
    else:
        status_message = (
            f"Status Checkpoint: {checkpoint_status} (Status pelatihan checkpoint tidak tercatat pada metadata. "
            "Hasil prediksi tidak dapat dipastikan apakah dari model terlatih atau inisialisasi acak)."
        )

    return {
        "text_input": text,
        "tokenized_sequence": seq_tokens,
        "num_tokens": total_seq_len,
        "num_masks": len(mask_positions),
        "mask_positions": mask_positions,
        "num_unk_tokens": len(unk_words),
        "unk_words": unk_words,
        "device_used": selected_device.type,
        "predictions": predictions_per_mask,
        "checkpoint_status": checkpoint_status,
        "status_message": status_message,
        "is_untrained_warning": status_message,
        "probability_note": (
            "Probabilitas dihitung melalui softmax atas seluruh vocabulary (8.000 kata). "
            "Token khusus dikecualikan dari pemeringkatan, dan nilai probabilitas yang ditampilkan "
            "adalah probabilitas absolut dari distribusi penuh tanpa normalisasi ulang."
        ),
        "multi_mask_note": (
            "Catatan Multi-Mask: Jika terdapat lebih dari satu [MASK], setiap posisi dievaluasi "
            "secara paralel dari konteks masukan yang sama, bukan merupakan prediksi gabungan autoregresif."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Skrip inferensi prediksi token [MASK] Mini-BERT Bahasa Indonesia"
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="scratch/random_init_smoke_test",
        help="Direktori checkpoint model (memuat model.pt dan config.json)",
    )
    parser.add_argument(
        "--tokenizer-dir",
        type=str,
        default="data/processed/pilot",
        help="Direktori artefak tokenizer (memuat vocab.json)",
    )
    parser.add_argument(
        "--text",
        type=str,
        required=True,
        help="Kalimat masukan bahasa Indonesia yang memuat token [MASK]",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Jumlah kandidat kata teratas yang ditampilkan untuk setiap [MASK]",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["cpu", "cuda", "auto"],
        help="Perangkat keras komputasi yang digunakan",
    )
    args = parser.parse_args()

    try:
        results = predict_mask(
            text=args.text,
            checkpoint_dir=args.checkpoint_dir,
            tokenizer_dir=args.tokenizer_dir,
            top_k=args.top_k,
            device=args.device,
        )
    except Exception as exc:
        print(f"\n[ERROR INFERENSI]: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n================ HASIL INFERENSI MINI-BERT ================")
    print(f"Kalimat Input     : {results['text_input']}")
    print(f"Device            : {results['device_used']}")
    print(f"Total Token       : {results['num_tokens']}")
    print(f"Jumlah [MASK]     : {results['num_masks']}")
    print(f"Status Checkpoint : {results['checkpoint_status']}")

    if results['num_unk_tokens'] > 0:
        print(f"Kata di Luar Vocabulary ([UNK]): {results['num_unk_tokens']} kata {results['unk_words']}")

    print("\n" + results['status_message'])
    print(results['probability_note'])
    if results['num_masks'] > 1:
        print(results['multi_mask_note'])

    for mask_info in results['predictions']:
        pos = mask_info['sequence_position']
        print(f"\n--- Prediksi untuk [MASK] pada Posisi Urutan {pos} ---")
        for cand in mask_info['candidates']:
            pct = cand['probability'] * 100.0
            print(f"  Peringkat {cand['rank']:2d} | Token ID: {cand['token_id']:5d} | Kata: '{cand['token']}' | Probabilitas: {pct:6.3f}% ({cand['probability']:.6f})")

    print("===========================================================\n")


if __name__ == "__main__":
    main()

