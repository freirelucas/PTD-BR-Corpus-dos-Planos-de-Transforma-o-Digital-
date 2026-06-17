# ============================================================
# CÉLULA 2 — Configuração, Constantes e Estruturas de Dados
# ============================================================
import os, sys, time, pickle, unicodedata, re, json, logging, difflib
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path
from datetime import datetime

import requests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm.auto import tqdm

# --------------- URLs e parâmetros de rede ------------------
BASE_URL = ("https://www.gov.br/governodigital/pt-br/"
            "estrategias-e-governanca-digital/"
            "planos-de-transformacao-digital")
REQUEST_DELAY = 2.0        # segundos entre requests ao gov.br
MAX_RETRIES   = 4
REQUEST_TIMEOUT = 90
HTTP_HEADERS  = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
}

# --------------- Vocabulários canônicos ---------------------
CANONICAL_EIXOS = [
    "Serviços Digitais e Melhoria da Qualidade",
    "Unificação de Canais Digitais",
    "Governança e Gestão de Dados",
    "Segurança e Privacidade",
    "Projetos Especiais",
]

# Mapa Eixo → lista de Produtos (44 produtos oficiais)
CANONICAL_PRODUTOS: Dict[str, List[str]] = {
    "Serviços Digitais e Melhoria da Qualidade": [
        "Disponibilização em Acesso Digital",
        "Disponibilização de datas/cronograma na Agenda Gov.Br",
        "Evolução do Serviço",
        "Implantação da Área Logada Gov.Br",
        "Implantação da Experiência LabQ",
        "Implementação do VLIBRAS",
        "Integração à ferramenta de acompanhamento das solicitações",
        "Integração à ferramenta de avaliação da satisfação dos usuários",
        "Realização de Autodiagnóstico de Qualidade",
        "Revisão da descrição dos serviços",
        "Oferta de agendamento digital",
        "Integração à ferramenta de solicitação de atendimento presencial",
        "Implantação do Atendimento Virtual",
    ],
    "Unificação de Canais Digitais": [
        "Implantação do Design System",
        "Integração ao Login Único",
        "Integração ao Pagtesouro",
        "Integração com Assinatura Digital Gov.br",
        "Migração de APPs móveis para a loja do Gov.br",
        "Migração de Portal Institucional",
        "Migração de Serviço para Plataforma Unificada",
    ],
    "Governança e Gestão de Dados": [
        "Abertura de bases de dados",
        "Adequação à LGPD",
        "Catalogação de bases de dados no Portal de Dados",
        "Criação de Comitê de Governança de Dados",
        "Elaboração de Plano de Dados Abertos",
        "Elaboração do PDTIC",
        "Elaboração/Revisão da POSIC",
        "Implantação de processo de gestão de dados",
        "Implantação do inventário de bases de dados",
        "Implementação da interoperabilidade de dados",
        "Integração de dados ao Conecta Gov.br",
        "Integração de dados ao Datamart",
        "Melhoria da qualidade de bases de dados",
        "Nomeação de Encarregado de Dados Pessoais",
        "Obtenção de certificação de bases de dados",
        "Publicação de dados no Portal de Dados Abertos",
        "Realização de Inventário de Dados",
        "Relatório de Impacto à Proteção de Dados Pessoais",
        "Resposta a demandas de compartilhamento",
        "Utilização de dados do Conecta Gov.br",
    ],
    "Segurança e Privacidade": [
        "Adequação ao Framework de Privacidade e Segurança da Informação",
        "Elevação do nível de maturidade em privacidade e segurança",
    ],
    "Projetos Especiais": [
        "Iniciativa de Transformação Digital",
        "Projeto Especial de Transformação Digital",
    ],
}

# ---------- Produtos de templates anteriores (v1.x, v2.x) -----
# Produtos que aparecem em PTDs mais antigos e não estão no template v4.0
# Mapeados ao canônico mais próximo ou mantidos como produto válido extra
LEGACY_PRODUTOS: Dict[str, List[str]] = {
    "Segurança e Privacidade": [
        "Implementação do PPSI",                             # template v2.x
        "Adequação ao PPSI",                                 # variante
        "Auto-avaliação, análise de lacunas e planejamento do PPSI",
    ],
    "Governança e Gestão de Dados": [
        "Integração à base de dados",                        # template v2.x genérico
        "Interoperabilidade de Sistemas",                    # eixo antigo EGD 2020
        "Compartilhamento de dados via Conecta Gov.br",      # variante
    ],
    "Serviços Digitais e Melhoria da Qualidade": [
        "Digitalização de Serviço",                          # EGD 2020-2022
        "Publicação de Serviço no Portal Gov.br",            # EGD 2020-2022
        "Transformação Digital de Serviço",                   # EGD 2020-2022
    ],
    "Projetos Especiais": [
        "Ação estratégica de transformação digital",         # variante
        "Outros",                                            # produto genérico usado por 39 órgãos
    ],
}

# ---------- Aliases: texto variante → canônico exato ----------
# Mapeamento determinístico de variações conhecidas
PRODUTO_ALIASES: Dict[str, str] = {
    # Truncamentos e variações de acentuação
    "Integração à ferramenta de avaliação da satisfação dos usuários dos serviços":
        "Integração à ferramenta de avaliação da satisfação dos usuários",
    "Evolução do Serviço Digital":
        "Evolução do Serviço",
    "Integração ao Login Único Gov.Br":
        "Integração ao Login Único",
    "Integração ao Login Unico":
        "Integração ao Login Único",
    "Implementação do VLibras":
        "Implementação do VLIBRAS",
    "Implementacao do VLIBRAS":
        "Implementação do VLIBRAS",
    "Implantação da Area Logada Gov.Br":
        "Implantação da Área Logada Gov.Br",
    "Migração de Serviço para Plataforma Unificada Gov.br":
        "Migração de Serviço para Plataforma Unificada",
    "Migração do Portal Institucional":
        "Migração de Portal Institucional",
    "Adequação à Lei Geral de Proteção de Dados":
        "Adequação à LGPD",
    "Elaboração do Plano Diretor de TIC":
        "Elaboração do PDTIC",
    "Elaboração da POSIC":
        "Elaboração/Revisão da POSIC",
    "Revisão da POSIC":
        "Elaboração/Revisão da POSIC",
    "Integração à ferramenta de acompanhamento de solicitações":
        "Integração à ferramenta de acompanhamento das solicitações",
    "Disponibilização em acesso digital":
        "Disponibilização em Acesso Digital",
    "Revisão da descrição de serviços":
        "Revisão da descrição dos serviços",
    # Variantes ortográficas observadas em PDFs gov.br 2024-2026
    "Autoavaliação, análise de lacunas e planejamento do PPSI":
        "Auto-avaliação, análise de lacunas e planejamento do PPSI",
    # Truncamentos de célula PDF (largura fixa corta o fim do texto) —
    # observados no snapshot 2026-05; cobrem ~430 dos 531 fuzzy_high.
    "Integração à ferramenta de avaliação da":
        "Integração à ferramenta de avaliação da satisfação dos usuários",
    "Integração à base de dados (outros)":
        "Integração à base de dados",
    "Auto-avaliação, análise de lacunas e pla":
        "Auto-avaliação, análise de lacunas e planejamento do PPSI",
    "Migração de Serviço para Plataforma":
        "Migração de Serviço para Plataforma Unificada",
    "Disponibilização em Acesso D":
        "Disponibilização em Acesso Digital",
    "Implantação da Área Logada":
        "Implantação da Área Logada Gov.Br",
    # Artefato de quebra de linha: caractere da célula vizinha colado no
    # início do produto (normalize_text não remove letra solta inicial).
    "eIntegração ao Login Único":
        "Integração ao Login Único",
    "eDisponibilização em Acesso Digital":
        "Disponibilização em Acesso Digital",
    "eIntegração à ferramenta de avaliação da":
        "Integração à ferramenta de avaliação da satisfação dos usuários",
    # Legacy / EGD 2020 mappings
    "Digitalização de Serviço":
        "Disponibilização em Acesso Digital",
    "Publicação de Serviço no Portal Gov.br":
        "Disponibilização em Acesso Digital",
    "Transformação Digital de Serviço":
        "Disponibilização em Acesso Digital",
}

# ---------- Eixos legados (EGD 2020-2022) → canônico ----------
EIXO_ALIASES: Dict[str, str] = {
    "Transformação Digital de Serviços Públicos":
        "Serviços Digitais e Melhoria da Qualidade",
    "Transformação Digital dos Serviços":
        "Serviços Digitais e Melhoria da Qualidade",
    "Unificação de Canais Digitais e Plataformas":
        "Unificação de Canais Digitais",
    "Governo como Plataforma":
        "Unificação de Canais Digitais",
    "Governo Aberto e Transparência":
        "Governança e Gestão de Dados",
    "Infraestrutura de TIC e Governança de Dados":
        "Governança e Gestão de Dados",
    "Interoperabilidade de Sistemas":
        "Governança e Gestão de Dados",
    "Dados para o Desenvolvimento":
        "Governança e Gestão de Dados",
    "Identidade Digital do Cidadão":
        "Unificação de Canais Digitais",
    "Governo Inteligente":
        "Projetos Especiais",
    # Typo observado em PDF do PGFN
    "Governaça e Gestão de Dados":
        "Governança e Gestão de Dados",
    # Artefatos de extração PDF: início truncado ('Ser' cortado) e/ou
    # caractere da célula vizinha colado (quebra de linha).
    "iviços Digitais e Melhoria da Qualidade":
        "Serviços Digitais e Melhoria da Qualidade",
    "iServiços Digitais e Melhoria da Qualidade":
        "Serviços Digitais e Melhoria da Qualidade",
    "pSegurança e Privacidade":
        "Segurança e Privacidade",
}

# Lista flat de todos os produtos (canônicos + legados)
ALL_PRODUTOS = [p for prods in CANONICAL_PRODUTOS.values() for p in prods]
ALL_PRODUTOS += [p for prods in LEGACY_PRODUTOS.values() for p in prods]

# Mapa reverso: produto → eixo canônico (canônicos + legados)
PRODUTO_TO_EIXO = {}
for eixo, prods in CANONICAL_PRODUTOS.items():
    for p in prods:
        PRODUTO_TO_EIXO[p] = eixo
for eixo, prods in LEGACY_PRODUTOS.items():
    for p in prods:
        PRODUTO_TO_EIXO[p] = eixo

# Thresholds de qualidade — usados por 11b_statistics.py para detectar regressões
# (ex: dedup pulado, checkpoint stale carregado, novo formato de PDF não suportado).
# Bumpar conforme o corpus crescer ou o gov.br republicar com novos rótulos.
QUALITY_THRESHOLDS = {
    "max_entregas":               4700,   # 4574 baseline + margem para PDFs novos
    "max_riscos":                  700,   # 619 baseline + margem
    "min_prob_canonica_ratio":    0.85,
    "min_imp_canonica_ratio":     0.85,
    "min_trat_canonica_ratio":    0.80,
}

# Escalas do Documento Diretivo (tabela de riscos)
PROBABILIDADE_SCALE = [
    "raro", "pouco provável", "provável",
    "muito provável", "praticamente certo",
]
IMPACTO_SCALE = [
    "muito baixo", "baixo", "médio", "alto", "muito alto",
]
TRATAMENTO_OPTIONS = ["mitigar", "eliminar", "transferir", "aceitar"]

# Aliases de escala — mapeamento semântico de variações metodológicas
# usadas por alguns órgãos para os 5 níveis canônicos da SGD.
# - ANTAQ usa 3 pontos (Baixa/Média/Alta) → comprime para níveis intermediários
# - SUSEP usa numérica 1-4 (omite o 5° nível) → aproxima ao final da escala
# - CADE mistura numerada com label (1-Alto, 2-Alto)
PROBABILIDADE_ALIASES: Dict[str, str] = {
    # ANTAQ 3-pontos
    "muito baixa": "raro",
    "baixa": "pouco provável",
    "media": "provável",
    "média": "provável",
    "alta": "muito provável",
    "muito alta": "praticamente certo",
    # SUSEP numérica
    "1": "raro",
    "2": "pouco provável",
    "3": "provável",
    "4": "muito provável",
    "5": "praticamente certo",
    # Variantes lexicais
    "rara": "raro",
    "raros": "raro",
    "raras": "raro",
    "praticamente certa": "praticamente certo",
    # Observadas em PDFs gov.br 2024-2026
    "pouca": "pouco provável",
    "certo": "praticamente certo",
    "baixo": "pouco provável",       # variante masculina ocasional
    "provavel muito": "muito provável",   # MMULHERES — ordem PT invertida
    "provavel pouco": "pouco provável",   # MMULHERES — idem
}
IMPACTO_ALIASES: Dict[str, str] = {
    # ANTAQ
    "grande": "muito alto",
    "moderado": "médio",
    "moderada": "médio",
    # CADE com prefixo numérico
    "1-alto": "alto",
    "2-alto": "alto",
    "1-medio": "médio",
    "1-médio": "médio",
    "2-medio": "médio",
    "2-médio": "médio",
    # SUSEP numérica (mesmo mapping da probabilidade)
    "1": "muito baixo",
    "2": "baixo",
    "3": "médio",
    "4": "alto",
    "5": "muito alto",
    # Variantes lexicais
    "baixa": "baixo",
    "media": "médio",
    "média": "médio",
    "alta": "alto",
    "muito baixa": "muito baixo",
    "muito alta": "muito alto",
    # Observadas em PDFs gov.br 2024-2026
    "crítico": "muito alto",
    "critico": "muito alto",
    "alto muito": "muito alto",       # ordem trocada por quebra de linha
    "muito alto alto": "muito alto",  # duplicação por quebra de linha
    "medio muito": "médio",           # MMULHERES — ordem trocada por quebra de linha
}
TRATAMENTO_ALIASES: Dict[str, str] = {
    "mitigar o risco": "mitigar",
    "reduzir": "mitigar",
    "reduzir ou mitigar": "mitigar",
    "reduzir ou mitigar o risco": "mitigar",
    "tratar": "mitigar",
    "monitorar": "mitigar",
    "tolerar": "aceitar",
    "aceitar ou tolerar": "aceitar",
    "aceitar ou tolerar o risco": "aceitar",
    "compartilhar": "transferir",
    "compartilhar o risco": "transferir",
    "compartilh ar": "transferir",   # quebra de linha intra-palavra
    "evitar": "eliminar",
    "mitigar/transferir": "mitigar; transferir",  # AEB — separador "/"
    "transferir/compartilhar": "transferir",      # ANA — variante "/"
    "3-mitigar": "mitigar",                       # CADE — prefixo numérico
}

# ---------- Órgãos que compartilham PDFs (grupos) ----------
ORGAN_GROUPS: Dict[str, List[str]] = {
    "MD":   ["MD", "CEX", "CM", "COMAER", "CENSIPAM", "FOSORIO", "HFA"],
    "MEC":  ["MEC", "CAPES", "EBSERH", "FNDE", "FUNDAJ", "IBC", "INEP", "INES"],
    "MF":   ["MF", "RFB", "STN", "PGFN"],
    "MMA":  ["MMA", "IBAMA", "ICMBIO", "SFB", "JBRJ"],
    "MT":   ["MT", "ANTT", "DNIT"],
    "MIDR": ["MIDR", "CODEVASF", "SUDAM", "SUDECO", "SUDENE"],
    "MDA":  ["MDA", "CONAB"],
}
# Reverso: sigla membro → sigla cabeça do grupo
MEMBER_TO_GROUP = {}
for head, members in ORGAN_GROUPS.items():
    for m in members:
        if m != head:
            MEMBER_TO_GROUP[m] = head

# --------------- Dataclasses --------------------------------
@dataclass
class OrganInfo:
    sigla: str
    nome_completo: str
    grupo: Optional[str] = None          # sigla do cabeça, se agrupado
    url_diretivo: Optional[str] = None
    url_entregas: Optional[str] = None
    pdf_path_diretivo: Optional[str] = None
    pdf_path_entregas: Optional[str] = None

@dataclass
class RiskEntry:
    orgao_sigla: str
    risco_texto: str = ""
    probabilidade_original: str = ""
    probabilidade_normalizada: str = ""
    probabilidade_score: float = 0.0
    probabilidade_method: str = ""    # exact | alias | fuzzy_high | fuzzy_low | unmatched
    impacto_original: str = ""
    impacto_normalizado: str = ""
    impacto_score: float = 0.0
    impacto_method: str = ""
    tratamento_original: str = ""
    tratamento_normalizado: str = ""
    tratamento_score: float = 0.0
    tratamento_method: str = ""
    acoes_tratamento: str = ""
    extraction_confidence: str = "high"    # high / medium / low
    needs_review: bool = False
    review_reason: Optional[str] = None

@dataclass
class DeliveryEntry:
    orgao_sigla: str
    tabela_tipo: str = "pactuada"          # default; "concluida" / "cancelada" quando os PTDs publicarem ciclos futuros
    servico_acao: str = ""
    produto_original: str = ""
    produto_normalizado: str = ""
    produto_score: float = 0.0
    produto_method: str = ""               # exact | alias | fuzzy_high | fuzzy_low | unmatched
    eixo_original: str = ""
    eixo_normalizado: str = ""
    eixo_score: float = 0.0
    eixo_method: str = ""
    area_responsavel: Optional[str] = None
    data_pactuada: Optional[str] = None
    data_entrega: Optional[str] = None
    pactuado: Optional[str] = None         # Sim / Não (concluídas)
    justificativa: Optional[str] = None    # (canceladas)
    extraction_confidence: str = "high"
    needs_review: bool = False
    review_reason: Optional[str] = None

@dataclass
class ProcessingError:
    orgao_sigla: str
    document_type: str     # diretivo / entregas
    stage: str             # download / extraction / standardization
    error_type: str
    error_message: str
    timestamp: str = ""
    url: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

# Contêineres globais
all_organs: List[OrganInfo] = []
all_risks: List[RiskEntry] = []
all_deliveries: List[DeliveryEntry] = []
all_errors: List[ProcessingError] = []

print(f"Configuração carregada: {len(ALL_PRODUTOS)} produtos canônicos em {len(CANONICAL_EIXOS)} eixos")