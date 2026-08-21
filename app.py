"""
LeveAgro - API de Precificacao de Fertilizantes
================================================
Deploy: Railway / Render / Heroku
"""

import os
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import sqlite3
from pathlib import Path

# ===========================================================================
# APP
# ===========================================================================

app = FastAPI(title="LeveAgro Pricing API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caminho do banco
DB_PATH = Path(__file__).parent / "leveagro_pricing.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ===========================================================================
# MODELOS
# ===========================================================================

class CotacaoRequest(BaseModel):
    formula: str = "NPK 04-14-08"
    data: str = "2026-08-01"
    uf_destino: str = "MT"
    quantidade_ton: float = 1000
    embalagem: str = "GRANEL"
    dias_prazo: int = 0
    spread_cdi: float = 2.0
    distancia_km: float = 1500

class SimulacaoRequest(BaseModel):
    formula: str = "NPK 04-14-08"
    horizonte_meses: int = 12
    n_simulacoes: int = 3000
    embalagem: float = 0
    distancia_km: float = 1500
    dias_prazo: int = 0

# ===========================================================================
# DADOS DE MERCADO
# ===========================================================================

# Precos atuais e parametros calibrados
MPs = {
    'KCL':   {'preco': 458, 'mu': 388, 'sigma': 0.0944, 'theta': 0.231},
    'MAP':   {'preco': 951, 'mu': 820, 'sigma': 0.1423, 'theta': 0.231},
    'SA':    {'preco': 301, 'mu': 232, 'sigma': 0.1631, 'theta': 0.231},
    'SSP':   {'preco': 315, 'mu': 272, 'sigma': 0.1427, 'theta': 0.231},
    'TSP':   {'preco': 653, 'mu': 564, 'sigma': 0.1427, 'theta': 0.231},
    'UREIA': {'preco': 571, 'mu': 442, 'sigma': 0.1658, 'theta': 0.231}
}

CAMBIO = {'preco': 5.08, 'mu': 0.0561, 'sigma': 0.1509}
SELIC = {'preco': 14.15, 'mu': 10.05, 'sigma': 1.35, 'kappa': 0.231}

FORMULAS = {
    'NPK 04-14-08': {'KCL': 13, 'MAP': 3, 'SA': 18, 'SSP': 66},
    'NPK 10-10-10': {'KCL': 17, 'MAP': 22, 'SSP': 34, 'UREIA': 9, 'TSP': 18},
    'NPK 20-00-20': {'KCL': 33, 'SA': 48, 'UREIA': 19},
    'NPK 05-25-25': {'KCL': 42, 'MAP': 11, 'SSP': 27, 'TSP': 20},
    'NPK 00-20-20': {'KCL': 33, 'SSP': 45, 'TSP': 22},
    'NPK 08-20-20': {'KCL': 33, 'MAP': 17, 'SSP': 28, 'TSP': 22}
}

# Cholesky (correlacoes)
CORR_L = np.array([
    [1.0, 0, 0, 0, 0, 0, 0],
    [0.785, 0.619, 0, 0, 0, 0, 0],
    [0.871, -0.312, 0.378, 0, 0, 0, 0],
    [0.778, 0.615, -0.066, 0.113, 0, 0, 0],
    [0.778, 0.615, -0.066, 0.113, 0, 0, 0],
    [0.855, -0.339, 0.365, -0.086, 0, 0.138, 0],
    [-0.138, -0.026, 0.026, 0.038, 0, -0.053, 0.986]
])

CDI_DIARIO = 0.05164
FRETE_POR_KM = 0.19
ICMS_PCT = 5.0

# ===========================================================================
# HISTORICO (24 meses)
# ===========================================================================

HISTORICO_MPs = {
    'KCL': {
        'datas': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
        'precos': [338.5, 338.1, 342.2, 343.0, 351.9, 352.0, 354.5, 362.9, 362.8, 371.0, 374.4, 378.3, 383.4, 387.6, 388.7, 392.6, 382.9, 390.2, 395.8, 420.4, 447.1, 460.7, 456.3, 458.0]
    },
    'MAP': {
        'datas': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
        'precos': [720.0, 736.7, 742.1, 752.9, 752.0, 758.1, 765.9, 787.2, 790.9, 800.2, 846.1, 872.2, 904.6, 914.1, 903.5, 890.6, 809.3, 812.5, 824.9, 860.5, 927.2, 943.4, 952.8, 951.0]
    },
    'SA': {
        'datas': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
        'precos': [180.0, 175.9, 182.2, 181.6, 195.4, 192.5, 193.3, 201.4, 197.8, 207.1, 202.8, 203.7, 203.3, 207.1, 210.9, 220.0, 222.5, 234.2, 239.7, 270.5, 292.9, 307.6, 294.5, 301.0]
    },
    'SSP': {
        'datas': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
        'precos': [238.3, 244.2, 246.0, 249.7, 249.5, 251.4, 254.1, 261.1, 263.0, 266.1, 281.2, 289.6, 300.6, 303.9, 300.5, 296.3, 269.4, 269.9, 274.1, 283.5, 305.8, 312.6, 316.8, 315.0]
    },
    'TSP': {
        'datas': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
        'precos': [494.0, 506.3, 510.0, 517.6, 517.1, 521.1, 526.8, 541.4, 545.2, 551.6, 582.8, 600.4, 623.2, 630.0, 622.9, 614.1, 558.4, 559.6, 568.3, 587.6, 633.9, 648.1, 656.8, 653.0]
    },
    'UREIA': {
        'datas': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
        'precos': [346.6, 337.3, 349.1, 348.1, 373.3, 368.7, 369.6, 384.9, 375.1, 392.4, 385.3, 388.2, 386.1, 393.2, 399.5, 415.8, 419.7, 443.5, 453.4, 522.3, 562.6, 582.1, 553.1, 571.0]
    }
}

HISTORICO_CAMBIO = {
    'datas': ['2024-08', '2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'],
    'valores': [5.55, 5.44, 5.70, 5.87, 6.07, 5.94, 5.76, 5.73, 5.69, 5.66, 5.47, 5.56, 5.45, 5.51, 5.68, 5.81, 6.18, 5.94, 5.81, 5.75, 5.69, 5.66, 5.47, 5.08]
}

HISTORICO_SELIC = {
    'datas': ['2024-09', '2024-10', '2024-11', '2024-12', '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08'],
    'selic': [10.50, 10.65, 11.04, 11.77, 12.24, 13.15, 13.57, 14.15, 14.55, 14.74, 14.90, 14.90, 14.90, 14.90, 14.90, 14.90, 14.90, 14.90, 14.80, 14.64, 14.40, 14.29, 14.15, 13.95]
}

# Matriz de correlacao original (antes de Cholesky)
CORR_MATRIX = {
    'variaveis': ['KCL', 'MAP', 'SA', 'SSP', 'TSP', 'UREIA', 'CAMBIO'],
    'matriz': [
        [1.000, 0.785, 0.871, 0.778, 0.778, 0.855, -0.138],
        [0.785, 1.000, 0.616, 0.996, 0.996, 0.640, -0.151],
        [0.871, 0.616, 1.000, 0.632, 0.632, 0.991, -0.093],
        [0.778, 0.996, 0.632, 1.000, 1.000, 0.654, -0.145],
        [0.778, 0.996, 0.632, 1.000, 1.000, 0.654, -0.145],
        [0.855, 0.640, 0.991, 0.654, 0.654, 1.000, -0.115],
        [-0.138, -0.151, -0.093, -0.145, -0.145, -0.115, 1.000]
    ]
}

# ===========================================================================
# FUNCOES DE PRICING
# ===========================================================================

def calcular_preco_formula(formula: str) -> dict:
    """Calcula preco de uma formula NPK."""
    comp = FORMULAS.get(formula)
    if not comp:
        raise ValueError(f"Formula {formula} nao encontrada")

    detalhes = []
    total_usd = 0

    for mp, pct in comp.items():
        preco = MPs[mp]['preco']
        contrib = preco * pct / 100
        total_usd += contrib
        detalhes.append({
            'mp': mp,
            'pct': pct,
            'preco_usd': preco,
            'contrib_usd': contrib
        })

    return {
        'formula': formula,
        'preco_usd': total_usd,
        'preco_brl': total_usd * CAMBIO['preco'],
        'cambio': CAMBIO['preco'],
        'composicao': detalhes
    }

def calcular_cotacao_completa(req: CotacaoRequest) -> dict:
    """Calcula cotacao completa com todos os custos."""
    preco_info = calcular_preco_formula(req.formula)

    # Embalagem
    embalagens = {'GRANEL': 0, 'BIGBAG': 78, 'SACO50': 100}
    custo_emb = embalagens.get(req.embalagem, 0)

    # Frete
    frete = req.distancia_km * FRETE_POR_KM

    # Juros
    if req.dias_prazo > 0:
        taxa_diaria = CDI_DIARIO + (req.spread_cdi / 252)
        fator_juros = (1 + taxa_diaria / 100) ** req.dias_prazo
    else:
        fator_juros = 1.0

    # Calculos
    bruto_brl = preco_info['preco_usd'] * CAMBIO['preco']
    ex_factory = bruto_brl + custo_emb
    cif_avista = ex_factory + frete
    cif_juros = cif_avista * fator_juros
    preco_final = cif_juros * (1 + ICMS_PCT / 100)
    preco_total = preco_final * req.quantidade_ton

    return {
        'inputs': req.dict(),
        'mercado': {
            'cambio': CAMBIO['preco'],
            'cdi_diario': CDI_DIARIO,
            'selic': SELIC['preco']
        },
        'composicao': preco_info['composicao'],
        'calculo': {
            'preco_usd': preco_info['preco_usd'],
            'bruto_brl': bruto_brl,
            'embalagem': custo_emb,
            'ex_factory': ex_factory,
            'frete': frete,
            'cif_avista': cif_avista,
            'fator_juros': fator_juros,
            'cif_juros': cif_juros,
            'icms_pct': ICMS_PCT,
            'preco_final': preco_final,
            'preco_total': preco_total
        }
    }

# ===========================================================================
# FUNCOES DE SIMULACAO
# ===========================================================================

def simular_ou(S0, mu, sigma, theta, T, dW):
    """Simula Ornstein-Uhlenbeck."""
    dt = 1/12
    path = [S0]
    X = np.log(S0)
    mu_log = np.log(mu)

    for t in range(T):
        e = np.exp(-theta * dt)
        std = sigma * np.sqrt((1 - e*e) / (2*theta))
        X = X * e + mu_log * (1 - e) + std * dW[t]
        path.append(np.exp(X))

    return np.array(path)

def simular_gbm(S0, mu, sigma, T, dW):
    """Simula Geometric Brownian Motion."""
    dt = 1/12
    path = [S0]
    S = S0

    for t in range(T):
        S = S * np.exp((mu - 0.5*sigma*sigma)*dt + sigma*np.sqrt(dt)*dW[t])
        path.append(S)

    return np.array(path)

def rodar_simulacao(req: SimulacaoRequest) -> dict:
    """Executa simulacao Monte Carlo."""
    formula = req.formula
    horizonte = req.horizonte_meses
    n_sim = req.n_simulacoes
    comp = FORMULAS.get(formula)

    if not comp:
        raise ValueError(f"Formula {formula} nao encontrada")

    # Custos fixos
    embalagem = req.embalagem
    frete = req.distancia_km * FRETE_POR_KM
    if req.dias_prazo > 0:
        taxa_diaria = CDI_DIARIO + 2.0/252
        fator_juros = (1 + taxa_diaria / 100) ** req.dias_prazo
    else:
        fator_juros = 1.0

    # Arrays para resultados
    npk_paths = []
    mp_names = ['KCL', 'MAP', 'SA', 'SSP', 'TSP', 'UREIA']

    for sim in range(n_sim):
        # Choques correlacionados
        Z = np.random.standard_normal((horizonte, 7))
        dW = Z @ CORR_L.T

        # Simular MPs
        mp_paths = {}
        for i, mp in enumerate(mp_names):
            p = MPs[mp]
            mp_paths[mp] = simular_ou(p['preco'], p['mu'], p['sigma'], p['theta'], horizonte, dW[:, i])

        # Simular cambio
        cambio_path = simular_gbm(CAMBIO['preco'], CAMBIO['mu'], CAMBIO['sigma'], horizonte, dW[:, 6])

        # Calcular NPK completo
        npk_path = []
        for t in range(horizonte + 1):
            preco_usd = sum(mp_paths[mp][t] * comp.get(mp, 0) / 100 for mp in mp_names)
            bruto = preco_usd * cambio_path[t]
            ex_fact = bruto + embalagem
            cif = ex_fact + frete
            cif_j = cif * fator_juros
            final = cif_j * (1 + ICMS_PCT / 100)
            npk_path.append(final)

        npk_paths.append(npk_path)

    npk_paths = np.array(npk_paths)

    # Estatisticas
    precos_finais = npk_paths[:, -1]

    # Percentis por tempo
    percentis = {
        'p5': np.percentile(npk_paths, 5, axis=0).tolist(),
        'p25': np.percentile(npk_paths, 25, axis=0).tolist(),
        'p50': np.percentile(npk_paths, 50, axis=0).tolist(),
        'p75': np.percentile(npk_paths, 75, axis=0).tolist(),
        'p95': np.percentile(npk_paths, 95, axis=0).tolist()
    }

    # Preco atual
    preco_atual = calcular_cotacao_completa(CotacaoRequest(
        formula=formula,
        embalagem='GRANEL' if embalagem == 0 else 'BIGBAG',
        distancia_km=req.distancia_km,
        dias_prazo=req.dias_prazo
    ))['calculo']['preco_final']

    return {
        'inputs': req.dict(),
        'preco_atual': preco_atual,
        'stats': {
            'media': float(np.mean(precos_finais)),
            'mediana': float(np.median(precos_finais)),
            'std': float(np.std(precos_finais)),
            'p5': float(np.percentile(precos_finais, 5)),
            'p25': float(np.percentile(precos_finais, 25)),
            'p75': float(np.percentile(precos_finais, 75)),
            'p95': float(np.percentile(precos_finais, 95))
        },
        'percentis': percentis,
        'histograma': {
            'bins': np.histogram(precos_finais, bins=50)[1].tolist(),
            'counts': np.histogram(precos_finais, bins=50)[0].tolist()
        }
    }

# ===========================================================================
# ENDPOINTS
# ===========================================================================

@app.get("/")
async def home():
    return FileResponse(Path(__file__).parent / "index.html")

@app.get("/api/formulas")
async def listar_formulas():
    """Lista formulas disponiveis."""
    return {"formulas": list(FORMULAS.keys())}

@app.get("/api/preco/{formula}")
async def preco_formula(formula: str):
    """Retorna preco de uma formula."""
    try:
        return calcular_preco_formula(formula)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/cotacao")
async def cotacao(req: CotacaoRequest):
    """Calcula cotacao completa."""
    try:
        return calcular_cotacao_completa(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/simulacao")
async def simulacao(req: SimulacaoRequest):
    """Executa simulacao Monte Carlo."""
    try:
        return rodar_simulacao(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/mercado")
async def dados_mercado():
    """Retorna dados de mercado atuais."""
    return {
        'mps': {k: v['preco'] for k, v in MPs.items()},
        'cambio': CAMBIO['preco'],
        'selic': SELIC['preco'],
        'cdi_diario': CDI_DIARIO
    }

@app.get("/api/historico")
async def historico():
    """Retorna historico de 24 meses de todas as variaveis."""
    return {
        'mps': HISTORICO_MPs,
        'cambio': HISTORICO_CAMBIO,
        'selic': HISTORICO_SELIC
    }

@app.get("/api/parametros")
async def parametros():
    """Retorna parametros calibrados dos processos estocasticos."""
    return {
        'mps': {k: {'mu': v['mu'], 'sigma': v['sigma'], 'theta': v['theta']} for k, v in MPs.items()},
        'cambio': {'mu': CAMBIO['mu'], 'sigma': CAMBIO['sigma']},
        'selic': {'mu': SELIC['mu'], 'sigma': SELIC['sigma'], 'kappa': SELIC['kappa']},
        'correlacao': CORR_MATRIX,
        'cholesky': CORR_L.tolist()
    }

# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
