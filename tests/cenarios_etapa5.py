"""Cenarios ficticios da etapa 5, semeados com a conta de administracao (cnotini).

equipe: clinica com recepcao (docs/fake_clinic/clinica.md). Fuso America/Sao_Paulo,
antecedencia de 2 h a 60 dias, janela de 48 h, politica 'handoff', servico de 30 min.
Profissionais:
- prof e prof2: expediente da secao 6 (seg a qui 08-12 e 13:30-18, sex ate 17,
  sab 08-12);
- prof_contiguo: quinta 08-12 e 12-14, faixas contiguas, override de 90 min;
- prof_inativo: inativo;
- prof_sem_expediente: faz o servico, sem nenhuma faixa de expediente.
serv_outro nao e feito por prof.

solo: consultorio sem recepcao (docs/fake_clinic/consultorio_solo.md). Fuso
America/Manaus, antecedencia de 24 h a 30 dias, janela de 24 h, politica
'aceitar_e_marcar', seg a sex 09-17, servico de 30 min com override de 60 min.

sem_cadastro: sem linha em regras_agendamento, com expediente e servico. So a falta
de regras explica uma ConfiguracaoInvalida, entao um teste que leia as regras de
outra clinica falha.

2027-03-01 e uma segunda-feira. Em 2027, Sao Paulo e UTC-3 e Manaus e UTC-4.
"""
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import create_engine, text

from app.config import MIGRATION_DATABASE_URL

engine_admin = create_engine(MIGRATION_DATABASE_URL)

UTC = timezone.utc
AGORA = datetime(2027, 3, 1, 12, tzinfo=UTC)

EXPEDIENTE_EQUIPE = [
    *[(d, time(8), time(12)) for d in range(0, 6)],
    *[(d, time(13, 30), time(18)) for d in range(0, 4)],
    (4, time(13, 30), time(17)),
]
EXPEDIENTE_SOLO = [(d, time(9), time(17)) for d in range(0, 5)]
EXPEDIENTE_CONTIGUO = [(3, time(8), time(12)), (3, time(12), time(14))]

# Ordem de remocao respeita as FKs
_TABELAS = (
    "handoffs",
    "agendamentos",
    "jobs",
    "mensagens",
    "conversas",
    "log_auditoria",
    "horarios_trabalho",
    "regras_agendamento",
    "profissional_servicos",
    "servicos",
    "profissionais",
    "clinicas",
)


def _inserir(conexao, sql, **params):
    resultado = conexao.execute(text(sql), params)
    return resultado.scalar() if resultado.returns_rows else None


def _profissional(conexao, tenant, ativo=True):
    return _inserir(
        conexao,
        "INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, 'P', :a) RETURNING id",
        t=tenant,
        a=ativo,
    )


def _servico(conexao, tenant, duracao):
    return _inserir(
        conexao,
        "INSERT INTO servicos (tenant_id, nome, duracao_minutos, ativo) "
        "VALUES (:t, 'S', :d, true) RETURNING id",
        t=tenant,
        d=duracao,
    )


def _vincular(conexao, tenant, prof, serv, override=None):
    _inserir(
        conexao,
        "INSERT INTO profissional_servicos (tenant_id, profissional_id, servico_id, "
        "duracao_minutos) VALUES (:t, :p, :s, :o)",
        t=tenant,
        p=prof,
        s=serv,
        o=override,
    )


def _expediente(conexao, tenant, prof, faixas):
    for dia, ini, fim in faixas:
        _inserir(
            conexao,
            "INSERT INTO horarios_trabalho (tenant_id, profissional_id, dia_semana, "
            "hora_inicio, hora_fim, ativo) VALUES (:t, :p, :d, :i, :f, true)",
            t=tenant,
            p=prof,
            d=dia,
            i=ini,
            f=fim,
        )


def _clinica(conexao, fuso, regras):
    tenant = str(uuid.uuid4())
    _inserir(
        conexao,
        "INSERT INTO clinicas (tenant_id, nome, ativo, fuso) VALUES (:t, 'C', true, :f)",
        t=tenant,
        f=fuso,
    )
    if regras is not None:
        minima, maxima, janela, politica = regras
        _inserir(
            conexao,
            "INSERT INTO regras_agendamento (tenant_id, antecedencia_minima_horas, "
            "antecedencia_maxima_dias, janela_cancelamento_horas, "
            "politica_cancelamento_fora_janela) VALUES (:t, :mi, :ma, :j, :p)",
            t=tenant,
            mi=minima,
            ma=maxima,
            j=janela,
            p=politica,
        )
    return tenant


def semear():
    """Cria os tres cenarios e devolve os ids de cada um."""
    with engine_admin.begin() as conexao:
        tenant = _clinica(conexao, "America/Sao_Paulo", (2, 60, 48, "handoff"))
        serv = _servico(conexao, tenant, 30)
        serv_outro = _servico(conexao, tenant, 30)
        equipe = {"tenant": tenant, "serv": serv, "serv_outro": serv_outro}
        for nome, faixas, override, ativo in (
            ("prof", EXPEDIENTE_EQUIPE, None, True),
            ("prof2", EXPEDIENTE_EQUIPE, None, True),
            ("prof_contiguo", EXPEDIENTE_CONTIGUO, 90, True),
            ("prof_inativo", EXPEDIENTE_EQUIPE, None, False),
            ("prof_sem_expediente", [], None, True),
        ):
            prof = _profissional(conexao, tenant, ativo)
            _vincular(conexao, tenant, prof, serv, override)
            _expediente(conexao, tenant, prof, faixas)
            equipe[nome] = prof
        _vincular(conexao, tenant, equipe["prof2"], serv_outro)

        tenant = _clinica(conexao, "America/Manaus", (24, 30, 24, "aceitar_e_marcar"))
        prof = _profissional(conexao, tenant)
        serv = _servico(conexao, tenant, 30)
        _vincular(conexao, tenant, prof, serv, 60)
        _expediente(conexao, tenant, prof, EXPEDIENTE_SOLO)
        solo = {"tenant": tenant, "prof": prof, "serv": serv}

        tenant = _clinica(conexao, "America/Sao_Paulo", None)
        prof = _profissional(conexao, tenant)
        serv = _servico(conexao, tenant, 30)
        _vincular(conexao, tenant, prof, serv)
        _expediente(conexao, tenant, prof, EXPEDIENTE_EQUIPE)
        sem_cadastro = {"tenant": tenant, "prof": prof, "serv": serv}
    return {"equipe": equipe, "solo": solo, "sem_cadastro": sem_cadastro}


def limpar(cenarios):
    with engine_admin.begin() as conexao:
        for cenario in cenarios.values():
            for tabela in _TABELAS:
                conexao.execute(
                    text(f"DELETE FROM {tabela} WHERE tenant_id = :t"),
                    {"t": cenario["tenant"]},
                )


def agendamentos(tenant, **filtros):
    """Agendamentos da clinica, lidos pela administracao para as assercoes."""
    condicoes = "".join(f" AND {coluna} = :{coluna}" for coluna in filtros)
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT id, profissional_id, contato_telefone, inicio, fim, status, "
                f"cancelado_fora_da_janela FROM agendamentos WHERE tenant_id = :t{condicoes} "
                "ORDER BY id"
            ),
            {"t": tenant, **filtros},
        ).all()


def configurar_handoff(tenant, *, plantao=None, texto=None, prazo=None):
    """Configuracao de handoff da clinica (ADR 0009), gravada pela administracao."""
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "UPDATE clinicas SET telefone_plantao = :p, handoff_texto_paciente = :x, "
                "handoff_prazo_resposta_minutos = :m WHERE tenant_id = :t"
            ),
            {"t": tenant, "p": plantao, "x": texto, "m": prazo},
        )


def mensagem(tenant, contato):
    """Grava uma mensagem de entrada e devolve o id, para referencia em handoffs."""
    mensagem_id = uuid.uuid4().hex
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
                "VALUES (:id, :t, :tel, 'quero cancelar', 'entrada')"
            ),
            {"id": mensagem_id, "t": tenant, "tel": contato},
        )
    return mensagem_id


def agendamento_direto(tenant, prof, serv, contato, inicio, fim):
    """Agendamento gravado pela administracao, para clinicas em que o servico nao
    consegue criar (cadastro incompleto)."""
    with engine_admin.begin() as conexao:
        return conexao.execute(
            text(
                "INSERT INTO agendamentos (tenant_id, profissional_id, servico_id, "
                "contato_telefone, inicio, fim, status) "
                "VALUES (:t, :p, :s, :tel, :i, :f, 'agendado') RETURNING id"
            ),
            {"t": tenant, "p": prof, "s": serv, "tel": contato, "i": inicio, "f": fim},
        ).scalar()


def handoffs(tenant):
    """Handoffs da clinica, lidos pela administracao para as assercoes."""
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT h.*, c.contato_telefone FROM handoffs h "
                "JOIN conversas c ON c.tenant_id = h.tenant_id AND c.id = h.conversa_id "
                "WHERE h.tenant_id = :t ORDER BY h.id"
            ),
            {"t": tenant},
        ).all()
