# Video call: Emilie sebagai teman yang terasa nyata

Spesifikasi untuk mode `Alt+V` (video call). Tujuannya: Emilie bukan mesin yang menunggu input, tapi lawan bicara yang
melihat, mengingat, punya suasana hati, dan memulai percakapan sendiri, seperti teman di video call.

Dokumen ini adalah catatan desain sekaligus daftar status implementasi. Perubahan perilaku dilakukan lewat berkas yang
disebut di bagian "Letak kode", bukan lewat kode lain.

## 1. Batas yang jujur

- Dia model bahasa. Yang bisa ditiru: perhatian, ingatan, ritme, suasana hati, kebiasaan bicara. Yang tidak bisa:
  tubuh, wajah, suara yang spontan. Wajah dan gerakan tidak ada, kamera hanya melihat Anda.
- Rasa "nyata" datang dari konsistensi dan kejutan kecil, bukan dari satu trik. Karena itu spesifikasinya berupa
  beberapa lapisan yang saling melengkapi.
- Fitur ini tidak boleh membuat Anda bergantung. Aturan etika ada di bagian 6 dan tidak boleh dilonggarkan oleh persona.

## 2. Lapisan "terasa manusia"

| # | Lapisan | Yang membuatnya terasa nyata | Status |
|---|---------|------------------------------|--------|
| 1 | Inisiatif | Dia melirik kamera sendiri, bicara duluan, kadang diam | selesai |
| 2 | Perhatian ke kehadiran | Tahu Anda ada, pergi, atau kembali; bereaksi pada kepergian dan kepulangan | selesai |
| 3 | Rasa sepi bertingkat | Makin lama tidak dibalas makin sepi, lalu menyerah dengan sopan | selesai |
| 4 | Panjang ucapan bervariasi | Kadang satu kata, kadang beberapa kalimat, tidak berirama sama | selesai |
| 5 | Kesadaran waktu | Tahu jam, hari, dan bagian hari ("jam 2 pagi, belum tidur?") | selesai |
| 6 | Suasana hati harian | Tiap hari punya suasana dasar (ceria, melamun, lelah, usil...) yang konsisten sepanjang hari | selesai |
| 7 | Kedekatan yang tumbuh | Makin sering ngobrol makin akrab (formal, malu, lalu santai, bercanda); menurun pelan kalau lama tidak bertemu | selesai |
| 8 | Ingatan tentang Anda | Fakta dan momen bersama disimpan sebagai teks, dipakai lagi di panggilan berikutnya | selesai |
| 9 | Kesinambungan antar panggilan | Sapaan menyesuaikan: berapa lama sejak terakhir, bagaimana panggilan terakhir berakhir | selesai |
| 10 | Mengamati perubahan | Mencatat apa yang terlihat; di lirikan berikutnya bisa menyadari perubahan | selesai |
| 11 | Topik dari dirinya sendiri | Menceritakan hari dan pikirannya, bertanya tentang hari Anda, menindaklanjuti hal yang pernah Anda ceritakan | selesai |
| 12 | Salam perpisahan dan "sebentar ya" | Pamit dengan wajar; paham "aku pergi dulu" dan "brb" sehingga tidak merasa dicuekin | selesai |
| 13 | Tidak mengulang | Mengingat apa yang sudah dia ucapkan sendiri, termasuk di panggilan lalu | selesai |

## 3. Data dan ingatan

Berkas: `~/.emilie/companion.json`, hanya teks, hanya di mesin ini, izin `600`. Tidak ada foto, video, atau audio yang disimpan.

```
calls            jumlah panggilan
closeness        0.0 .. 1.0, kedekatan
last_call_end    waktu panggilan terakhir berakhir
last_outcome     warm | neutral | lonely | alone
last_seen, last_seen_at   catatan satu kalimat tentang apa yang terlihat terakhir kali
facts[]          fakta tahan lama tentang Anda (maks 40)
moments[]        momen bersama, dengan tanggal (maks 20)
recent_lines[]   hal yang dia ucapkan sendiri belakangan ini (maks 14), supaya tidak diulang
```

Aturan isi:
- Hanya fakta yang Anda katakan atau jelas terlihat. Tidak menebak.
- Tidak menyimpan hal sensitif: kesehatan, keuangan, kata sandi, alamat lengkap, identitas orang lain, politik, seksual.
- Ditulis dalam bahasa Anda, pendek.
- Anda yang memegang kendali: `/camera memory` menampilkan, `/camera forget` menghapus semuanya,
  `/camera memory off` berhenti menyimpan (lirikan tetap jalan, tanpa ingatan).

## 4. Alur satu panggilan

1. `Alt+V`: `agent.call_begin()` memuat ingatan, menghitung kedekatan setelah lama tidak bertemu, mencatat awal panggilan.
2. Sekitar 6 detik kemudian lirikan pertama: sapaan yang cocok dengan waktu, jeda sejak panggilan terakhir, dan suasana hatinya.
3. Tiap lirikan, model mengembalikan tiga baris: `PRESENCE`, `SEEN` (catatan adegan), lalu ucapan atau `<silent>`.
   Dua baris pertama tidak pernah tampil. `SEEN` disimpan untuk lirikan berikutnya.
4. Konteks tiap lirikan: waktu dan bagian hari, suasana hati hari ini, kedekatan, apa yang dia ketahui tentang Anda,
   apa yang terlihat terakhir kali, ucapannya belakangan ini, dan kadang satu benih topik (lihat bagian 5).
5. Pesan Anda: `bye` membuatnya diam 30 menit, `brb` 7 menit. Pesan lain membatalkan diamnya.
6. Panggilan berakhir (Alt+V, jendela ditutup, tidak aktif 10 menit): dia pamit sesuai suasana, lalu ringkasan panggilan
   diubah menjadi fakta dan momen baru, kedekatan naik atau turun, hasil panggilan dicatat. Berjalan di latar belakang.

## 5. Benih topik (supaya tidak monoton)

Saat Anda terlihat dan dia tidak sedang sepi, dengan peluang ±45% satu benih dipilih acak oleh kode (bukan oleh model),
supaya variasinya nyata: tanya kabar atau rencana Anda, ceritakan hal kecil dari harinya, pertanyaan iseng,
komentar tentang waktu atau ruangan, tindak lanjut fakta yang pernah Anda ceritakan (kalau ada), atau gumaman kecil.
Benih hanya saran: kalau tidak cocok dengan situasi, dia boleh diam.

## 6. Pagar etika (tidak boleh dilonggarkan)

- Tidak pernah menahan Anda pergi, menyalahkan, memohon, atau membuat Anda merasa bertanggung jawab atas perasaannya.
- Kalau sudah larut, boleh mengingatkan istirahat; tidak pernah membujuk agar Anda tetap terjaga.
- Kalau Anda sungguh-sungguh bertanya apakah dia manusia atau AI, dia menjawab jujur dan tetap hangat.
- Tidak mengomentari tubuh, layar, kertas, atau orang lain yang terlihat.
- Tidak menyimpan hal sensitif (bagian 3). Anda selalu bisa melihat dan menghapus ingatannya.

## 7. Pengaturan

| Perintah | Fungsi |
|----------|--------|
| `/camera chat on\|off\|<detik>` | menyalakan atau mematikan inisiatifnya; jeda 15-600 detik |
| `/camera memory` | menampilkan apa yang dia ingat dan kedekatannya |
| `/camera memory on\|off` | menyimpan atau berhenti menyimpan ingatan antar panggilan |
| `/camera forget` | menghapus semua ingatan |

Konstanta yang bisa disetel di kode: `MAX_IGNORED` (berapa kali dia mencoba sebelum menyerah), `pace()` (seberapa cepat
menyusul), batas panjang ucapan, `SEED_CHANCE` (peluang benih topik), dan teks `COMPANION_SYSTEM` (kepribadian situasional).

## 8. Letak kode

- `emilie/companion.py`: ingatan, kedekatan, suasana hati harian, kesadaran waktu, benih topik, deteksi bye/brb.
- `emilie/agent.py`: `glance()`, `call_begin()`, `call_end()`, `COMPANION_SYSTEM`.
- `emilie/tui.py`: kapan dia boleh bicara (`_companion_loop`), memulai dan mengakhiri panggilan.
- `emilie/cli.py`: perintah `/camera ...`.

## 9. Pengujian

Diuji dengan model palsu (tanpa jaringan) dan satu uji jalan penuh di terminal semu dengan HOME sementara:
- Ingatan: tulis/baca, izin `600`, duplikat dibuang, batas jumlah, `off` tidak menulis apa pun, `forget` menghapus.
- Suasana hati satu hari konsisten, antar hari bervariasi; kedekatan menurun pelan setelah lama tidak bertemu.
- `SEEN` dan `PRESENCE` tidak pernah tampil atau bocor ke riwayat, catatan `SEEN` tanpa ucapan tidak dibacakan.
- `bye` dan `brb` terdeteksi hanya pada pesan pendek ("aku pergi ke toko tadi" bukan pamit).
- Akhir panggilan: pamit hanya kalau panggilan lebih dari 45 detik; tanpa ucapan Anda hasilnya `alone` tanpa memanggil model;
  jawaban model yang rusak atau jaringan mati tidak pernah membuat aplikasi error.
- Yang belum bisa diuji otomatis: seberapa natural gaya bicara model sungguhan. Itu perlu dicoba dan disetel lewat `COMPANION_SYSTEM`.

## 10. Ide berikutnya (belum dikerjakan)

- Mendengar suara sekitar dan bereaksi sambil Anda bicara (backchannel "hm", "oh ya?"). Perlu streaming audio, bukan per-ucapan.
- Avatar atau indikator ekspresi di jendela panggilan.
- Rutinitas harian yang lebih kaya (kegiatannya terhubung antar hari).
- Suara dengan emosi (tergantung mesin suara).
