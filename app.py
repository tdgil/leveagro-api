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

# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
