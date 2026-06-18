#!/usr/bin/env python3
"""Parser de LISTAGEM DE RESERVAS (PDF) -> CSV.

Extrai registos multi-linha ancorados na coluna 'N.º Reserva' usando
as coordenadas x das palavras (pdfplumber.extract_words), mais robusto
que extract_tables (que descarta a 1ª linha de cada página).

Uso:
    python parse_reservas.py [input.pdf] [output.csv]

Por omissão: Reservas.pdf -> reservas.csv (+ reservas_full.csv)
"""

import sys
import csv
import re
from pathlib import Path

import pdfplumber

# Limites x das colunas (em pontos PDF, derivados do cabeçalho).
# (nome, x_min, x_max)
COLUMNS = [
    ("N_Reserva",     5,   60),
    ("Dt_Criacao",    65,  120),
    ("CNP",          125,  160),
    ("Produto",      162,  265),
    ("Cliente",      267,  345),
    ("Canal",        348,  450),
    ("N_Enc_Online", 391,  440),   # sobrepõe-se a 'Local Criação' verticalmente
    ("Local_Criacao", 454, 530),
    ("Qtd_Res",      533,  572),
    ("Stock",        575,  615),
    ("Operador",     617,  672),
    ("Faturada",     674,  713),
    ("Dt_Alteracao", 715,  776),
    ("Estado",       777,  820),
]

# Colunas pedidas pelo utilizador (ordem do CSV reduzido).
REQUESTED = ["Dt_Criacao", "CNP", "Produto", "Qtd_Res", "Faturada"]
REQUESTED_HEADER = ["Dt. Criação", "CNP", "Produto", "Qtd. Res.", "Faturada"]

# Cabeçalho legível para o CSV completo.
FULL_HEADER = [
    "N.º Reserva", "Dt. Criação", "CNP", "Produto", "Cliente", "Canal",
    "N.º Enc. Online", "Local Criação", "Qtd. Res.", "Stock", "Operador",
    "Faturada", "Dt. Alteração", "Estado",
]

# Topo (y) a partir do qual começa o conteúdo útil (abaixo do cabeçalho).
CONTENT_TOP = 170
# Base (y) do conteúdo útil (acima do rodapé 'Gerado em ... / Pág. X de Y').
CONTENT_BOTTOM = 548
# Rodapé a ignorar (linhas 'Gerado em ...' / 'Pág. X de Y').
FOOTER_RE = re.compile(r"(Gerado em|Pág\.|NIF:|LISTAGEM DE RESERVAS|De \d)", re.I)
# Token de hora com segundos (HH:MM:SS) — só aparece no rodapé 'Gerado em ...'.
HORA_COM_SEGUNDOS_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
ANCHOR_X_MIN, ANCHOR_X_MAX = 5, 35
# Deslocamento vertical (em pontos) entre o N.º Reserva (anchor) e a linha
# da data imediatamente acima. Cada registo ocupa a janela
# [anchor_top - LINE_ABOVE, next_anchor_top - LINE_ABOVE).
LINE_ABOVE = 6


def is_anchor(word):
    """True se a palavra for o N.º Reserva (inteiro 5-6 dígitos na margem esquerda)."""
    if not (ANCHOR_X_MIN <= word["x0"] <= ANCHOR_X_MAX):
        return False
    t = word["text"]
    return t.isdigit() and 5 <= len(t) <= 6


def bucket_words(words, col_defs):
    """Distribui palavras pelas colunas conforme x0 e junta texto multi-linha."""
    buckets = {name: [] for name, _, _ in col_defs}
    for w in words:
        x = w["x0"]
        for name, lo, hi in col_defs:
            if lo <= x < hi:
                buckets[name].append(w)
                break
    out = {}
    for name, _, _ in col_defs:
        ws = sorted(buckets[name], key=lambda w: (round(w["top"]), w["x0"]))
        # Agrupa por linha (top ~ igual) -> junta com espaço; linhas com '\n'.
        lines = []
        cur_top = None
        cur = []
        for w in ws:
            t = round(w["top"])
            if cur_top is None or abs(t - cur_top) <= 2:
                cur.append(w["text"])
                cur_top = t if cur_top is None else cur_top
            else:
                lines.append(" ".join(cur))
                cur = [w["text"]]
                cur_top = t
        if cur:
            lines.append(" ".join(cur))
        out[name] = "\n".join(lines).strip()
    return out


def clean(value, multiline=False):
    """Normaliza espaços; preserva newlines se multiline."""
    if multiline:
        return re.sub(r"[ \t]+", " ", value).strip()
    return re.sub(r"\s+", " ", value).strip()


def parse_pdf(path):
    """Lê o PDF e devolve lista de dicionários (um por registo)."""
    records = []
    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for pi, page in enumerate(pdf.pages, 1):
            words = page.extract_words()
            if not words:
                continue
            data_words = [w for w in words
                          if CONTENT_TOP < w["top"] < CONTENT_BOTTOM
                          and not FOOTER_RE.search(w["text"])
                          and not HORA_COM_SEGUNDOS_RE.match(w["text"])]
            anchors = [w for w in data_words if is_anchor(w)]
            anchors.sort(key=lambda w: w["top"])
            if not anchors:
                continue
            for i, anchor in enumerate(anchors):
                top = anchor["top"]
                # O registo inclui a data (linha ~4.8 pts acima do anchor) e
                # termina antes da data do próximo registo. Limita também a
                # ~32 pts de altura para não apanhar rodapé/outras linhas.
                bottom = (anchors[i + 1]["top"] - LINE_ABOVE
                          if i + 1 < len(anchors)
                          else top + 32)
                top_lo = top - LINE_ABOVE
                top_hi = min(bottom, top + 32)
                row_words = [w for w in data_words
                             if top_lo <= w["top"] < top_hi]
                row = bucket_words(row_words, COLUMNS)
                # Garante que o próprio anchor fica como N_Reserva.
                if not row["N_Reserva"]:
                    row["N_Reserva"] = anchor["text"]
                # Normalização por coluna.
                row["Dt_Criacao"] = clean(row["Dt_Criacao"])
                row["Dt_Alteracao"] = clean(row["Dt_Alteracao"])
                row["Produto"] = clean(row["Produto"])
                row["Cliente"] = clean(row["Cliente"])
                row["Operador"] = clean(row["Operador"])
                # Validação mínima.
                if not row["CNP"] or not row["Produto"]:
                    sys.stderr.write(
                        f"[aviso] pág {pi} registo {row.get('N_Reserva')}"
                        f" com campos em falta (CNP/Produto)\n")
                records.append(row)
            if pi % 10 == 0 or pi == n_pages:
                sys.stderr.write(f"  processadas {pi}/{n_pages} páginas"
                                 f" ({len(records)} registos)\n")
    return records


def write_csv(records, path, fields, header):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        for r in records:
            w.writerow([r.get(fld, "") for fld in fields])


def to_dataframe(records, fields=REQUESTED, header=REQUESTED_HEADER):
    """Converte registos do parse_pdf num pandas.DataFrame com colunas legíveis.

    fields : nomes internos das colunas a extrair (por defeito REQUESTED).
    header : nomes legíveis a atribuir (por defeito REQUESTED_HEADER).

    Devolve Dt. Criação como str (conversão para datetime fica a cargo do
    consumidor, como já acontece no main.py) e Qtd. Res. como numérico
    (NaN onde não for possível converter).
    """
    import pandas as pd
    if len(records) == 0:
        return pd.DataFrame(columns=header)
    df = pd.DataFrame([{h: r.get(f, "") for f, h in zip(fields, header)} for r in records])
    if "Qtd. Res." in df.columns:
        df["Qtd. Res."] = pd.to_numeric(df["Qtd. Res."], errors="coerce")
    return df


def main(argv):
    in_path = argv[1] if len(argv) > 1 else "Reservas.pdf"
    out_path = argv[2] if len(argv) > 2 else "reservas.csv"
    full_path = Path(out_path).with_name(
        Path(out_path).stem + "_full" + Path(out_path).suffix)

    if not Path(in_path).exists():
        sys.exit(f"Ficheiro não encontrado: {in_path}")

    print(f"A ler {in_path} ...")
    records = parse_pdf(in_path)
    print(f"Total de registos: {len(records)}")

    write_csv(records, out_path, REQUESTED, REQUESTED_HEADER)
    print(f"CSV reduzido: {out_path}")

    write_csv(records, str(full_path),
              [c[0] for c in COLUMNS], FULL_HEADER)
    print(f"CSV completo : {full_path}")


if __name__ == "__main__":
    main(sys.argv)