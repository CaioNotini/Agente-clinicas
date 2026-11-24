"""
app/db/models.py
Modelos SQLAlchemy — todas as tabelas
"""
# func.now() e gerado dinamicamente pelo SQLAlchemy, e o pylint o acusa como
# not-callable (E1102) por engano. Desligado so neste arquivo, para a regra
# continuar valendo no resto de app/.
# pylint: disable=not-callable

import uuid

from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.sql import func

from app.db.base import Base  # Importa de base.py, não de __init__


class Clinica(Base):
    __tablename__ = "clinicas"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    nome = Column(String(200), nullable=False)
    email = Column(String(200))
    telefone = Column(String(20))
    telefone_plantao = Column(String(20))
    # Fuso IANA da clinica. As regras de antecedencia, janela e lembretes usam este
    # fuso. O armazenamento continua em UTC (ADR 0009). Validado na leitura
    # (regras_da_clinica): a aplicacao ainda nao grava este campo.
    fuso = Column(
        String(40), nullable=False, server_default=text("'America/Sao_Paulo'")
    )
    # Configuracao do handoff como dado (ADR 0009). O destinatario do aviso e
    # telefone_plantao, da recepcao ou do proprio profissional.
    # NULL em prazo significa nao informar prazo ao paciente.
    handoff_prazo_resposta_minutos = Column(Integer)
    # NULL em texto significa usar um texto padrao neutro.
    handoff_texto_paciente = Column(String(500))
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())


class Profissional(Base):
    __tablename__ = "profissionais"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    nome = Column(String(200), nullable=False)
    especialidade = Column(String(200))
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        # Alvo das FKs compostas por tenant (ADR 0007)
        UniqueConstraint("tenant_id", "id", name="uq_profissionais_tenant_id_id"),
    )


class Servico(Base):
    __tablename__ = "servicos"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    nome = Column(String(200), nullable=False)
    duracao_minutos = Column(Integer, default=30)
    preco = Column(Float)
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        # Alvo das FKs compostas por tenant (ADR 0007)
        UniqueConstraint("tenant_id", "id", name="uq_servicos_tenant_id_id"),
    )


class HorarioTrabalho(Base):
    __tablename__ = "horarios_trabalho"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    profissional_id = Column(Integer, nullable=False)
    dia_semana = Column(Integer)  # 0=seg, 6=dom
    hora_inicio = Column(Time)
    hora_fim = Column(Time)
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_horarios_tenant", "tenant_id"),
        # FK composta: o registro pai precisa ser da mesma clinica (ADR 0007)
        ForeignKeyConstraint(
            ["tenant_id", "profissional_id"],
            ["profissionais.tenant_id", "profissionais.id"],
            name="fk_horarios_trabalho_profissional_id_tenant",
        ),
    )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    type = Column(
        String(50), nullable=False
    )  # PROCESS_INBOUND_MESSAGE, SEND_WHATSAPP, SEND_REMINDER, NOTIFY_HANDOFF
    status = Column(String(20), nullable=False, server_default=text("'pending'"))
    payload = Column(JSON)
    # Conversa do job, para a ordem por conversa (ADR 0005). NULL em jobs sem conversa.
    contato_telefone = Column(String(20))
    run_at = Column(DateTime, nullable=False, server_default=func.now())
    attempts = Column(Integer, nullable=False, server_default=text("0"))
    max_attempts = Column(Integer, nullable=False, server_default=text("3"))
    last_error = Column(String(500))
    locked_at = Column(DateTime)
    locked_by = Column(String(100))
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_jobs_status_run_at", "status", "run_at"),
        Index("idx_jobs_tenant", "tenant_id"),
        Index(
            "idx_jobs_conversa_pendentes",
            "tenant_id",
            "contato_telefone",
            "id",
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'done', 'dead')", name="ck_jobs_status"
        ),
        CheckConstraint(
            "type <> 'PROCESS_INBOUND_MESSAGE' OR contato_telefone IS NOT NULL",
            name="ck_jobs_mensagem_tem_conversa",
        ),
    )


class Mensagem(Base):
    __tablename__ = "mensagens"

    id = Column(String(100), primary_key=True)  # message_id
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    contato_telefone = Column(String(20), nullable=False)
    conteudo = Column(String(4096), nullable=False)
    direcao = Column(String(10))
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_mensagens_tenant_contato", "tenant_id", "contato_telefone"),
        CheckConstraint("direcao IN ('entrada', 'saida')", name="ck_mensagens_direcao"),
        # Alvo da FK composta de handoffs.mensagem_id (ADR 0007)
        UniqueConstraint("tenant_id", "id", name="uq_mensagens_tenant_id_id"),
    )


class Conversa(Base):
    __tablename__ = "conversas"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    contato_telefone = Column(String(20), nullable=False)
    # Estados de app/core/estados.py e do ADR 0003
    estado_conversa = Column(String(30), nullable=False, server_default=text("'idle'"))
    human_mode = Column(Boolean, nullable=False, server_default=text("false"))
    historico = Column(JSON)
    criada_em = Column(DateTime, server_default=func.now())
    atualizada_em = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "contato_telefone", name="uq_conversas_tenant_contato"
        ),
        # Alvo das FKs compostas por tenant (ADR 0007)
        UniqueConstraint("tenant_id", "id", name="uq_conversas_tenant_id_id"),
        CheckConstraint(
            "estado_conversa IN ('idle', 'coletando_info', 'aguardando_confirmacao', 'escalada', 'encerrada')",
            name="ck_conversas_estado",
        ),
    )


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    acao = Column(String(100), nullable=False)
    descricao = Column(String(500))
    dados = Column(JSON)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_auditoria_tenant_acao", "tenant_id", "acao"),)


# Regras de agendamento de cada clínica: antecedência e janela de cancelamento
class RegraAgendamento(Base):
    __tablename__ = "regras_agendamento"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    antecedencia_minima_horas = Column(Integer)
    antecedencia_maxima_dias = Column(Integer)
    janela_cancelamento_horas = Column(Integer)
    # Politica para cancelamento feito com menos antecedencia que a janela (Q-22,
    # ADR 0009). 'handoff' abre handoff e so cancela apos decisao humana.
    # 'aceitar_e_marcar' cancela na hora e marca cancelado_fora_da_janela.
    politica_cancelamento_fora_janela = Column(
        String(20), nullable=False, server_default=text("'handoff'")
    )
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_regras_tenant"),
        CheckConstraint(
            "politica_cancelamento_fora_janela IN ('handoff', 'aceitar_e_marcar')",
            name="ck_regras_politica_cancelamento",
        ),
    )


# Relação entre profissionais e os serviços que realizam
class ProfissionalServico(Base):
    __tablename__ = "profissional_servicos"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    profissional_id = Column(Integer, nullable=False)
    servico_id = Column(Integer, nullable=False)
    # Override opcional da duracao por profissional (Q-21, ADR 0009). NULL usa a
    # duracao padrao do servico.
    duracao_minutos = Column(Integer)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "profissional_id", "servico_id", name="uq_profissional_servico"
        ),
        Index("idx_profissional_servicos_tenant", "tenant_id"),
        # FK composta: o registro pai precisa ser da mesma clinica (ADR 0007)
        ForeignKeyConstraint(
            ["tenant_id", "profissional_id"],
            ["profissionais.tenant_id", "profissionais.id"],
            name="fk_profissional_servicos_profissional_id_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "servico_id"],
            ["servicos.tenant_id", "servicos.id"],
            name="fk_profissional_servicos_servico_id_tenant",
        ),
    )


# Contatos de pacientes: dado mínimo, sem prontuário
class PacienteContato(Base):
    __tablename__ = "pacientes_contatos"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    nome = Column(String(200))
    contato_telefone = Column(String(20), nullable=False)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "contato_telefone", name="uq_pacientes_tenant_contato"
        ),
    )


# Registro de cada handoff: quem foi avisado, quem assumiu e quando voltou ao bot
class Handoff(Base):
    __tablename__ = "handoffs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    conversa_id = Column(Integer, nullable=False)
    motivo = Column(String(50), nullable=False)
    notificado_em = Column(DateTime)
    # Quem de fato recebeu o aviso e por qual canal (Q-24, ADR 0009). O destinatario
    # vem de clinicas.telefone_plantao, nao de um papel fixo de recepcao.
    notificado_para = Column(String(100))
    notificado_canal = Column(String(20))
    assumido_por = Column(String(100))
    assumido_em = Column(DateTime)
    devolvido_em = Column(DateTime)
    criada_em = Column(DateTime, server_default=func.now())
    # Copia do texto que o bot informou ao paciente na abertura, nunca a mensagem do
    # paciente, e o limite calculado do prazo da clinica (revisao do ADR 0009)
    texto_paciente = Column(String(600))
    responder_ate = Column(DateTime(timezone=True))
    agendamento_id = Column(Integer)
    # So a referencia da mensagem de origem, nunca o conteudo
    mensagem_id = Column(String(100))

    __table_args__ = (
        Index("idx_handoffs_tenant", "tenant_id"),
        Index("idx_handoffs_conversa", "conversa_id"),
        CheckConstraint(
            "notificado_canal IN ('cli', 'whatsapp')",
            name="ck_handoffs_notificado_canal",
        ),
        # FK composta: o registro pai precisa ser da mesma clinica (ADR 0007)
        ForeignKeyConstraint(
            ["tenant_id", "conversa_id"],
            ["conversas.tenant_id", "conversas.id"],
            name="fk_handoffs_conversa_id_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agendamento_id"],
            ["agendamentos.tenant_id", "agendamentos.id"],
            name="fk_handoffs_agendamento_id_tenant",
        ),
        # Na migration o SET NULL tem a lista de colunas (mensagem_id): a exclusao da
        # mensagem (LGPD) zera so a referencia, e tenant_id continua preenchido. O
        # SQLAlchemy nao aceita a lista aqui, entao o schema vem sempre da migration.
        ForeignKeyConstraint(
            ["tenant_id", "mensagem_id"],
            ["mensagens.tenant_id", "mensagens.id"],
            name="fk_handoffs_mensagem_id_tenant",
            ondelete="SET NULL",
        ),
    )


# Histórico de consentimentos: uma linha por aceite, sem sobrescrever o anterior
class Consent(Base):
    __tablename__ = "consents"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    contato_telefone = Column(String(20), nullable=False)
    tipo = Column(String(50), nullable=False)
    versao_texto = Column(String(20), nullable=False)
    canal = Column(String(30))
    concedido_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_consents_tenant_contato", "tenant_id", "contato_telefone"),
    )


# Pedidos de privacidade do titular (acesso, correção, exclusão, portabilidade)
class PrivacyRequest(Base):
    __tablename__ = "privacy_requests"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    contato_telefone = Column(String(20), nullable=False)
    tipo = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False)
    criada_em = Column(DateTime, server_default=func.now())
    concluida_em = Column(DateTime)

    __table_args__ = (Index("idx_privacy_requests_tenant", "tenant_id"),)


# Agendamentos de consultas: profissional, servico, janela de tempo e status.
# inicio e fim sao timestamptz (com fuso, gravados em UTC). As demais tabelas usam
# timestamp sem fuso; esta e a excecao, registrada no ADR 0004 e na arquitetura.
# O conflito de horario e garantido pela constraint EXCLUDE, com a mesma semantica
# da funcao pura de conflito (intervalo semiaberto [inicio, fim)). Ver ADR 0004.
class Agendamento(Base):
    __tablename__ = "agendamentos"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False
    )
    profissional_id = Column(Integer, nullable=False)
    servico_id = Column(Integer, nullable=False)
    contato_telefone = Column(String(20), nullable=False)
    inicio = Column(DateTime(timezone=True), nullable=False)
    fim = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        String(20), nullable=False, server_default="agendado"
    )  # agendado (ativo) | cancelado
    # Marca de cancelamento tardio na politica 'aceitar_e_marcar' (Q-22, ADR 0009).
    cancelado_fora_da_janela = Column(
        Boolean, nullable=False, server_default=text("false")
    )
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        # Intervalo valido: fim sempre depois do inicio
        CheckConstraint("fim > inicio", name="ck_agendamentos_intervalo"),
        # Status restrito aos dois valores desta etapa
        CheckConstraint(
            "status IN ('agendado', 'cancelado')", name="ck_agendamentos_status"
        ),
        # Conflito: nenhum par de agendamentos ativos do mesmo profissional da mesma
        # clinica pode ter intervalos que se sobrepoem. Intervalo semiaberto, entao
        # horarios adjacentes nao conflitam. Precisa da extensao btree_gist para os
        # operadores de igualdade de tenant_id (uuid) e profissional_id (integer).
        ExcludeConstraint(
            ("tenant_id", "="),
            ("profissional_id", "="),
            (text("tstzrange(inicio, fim)"), "&&"),
            using="gist",
            where=text("status = 'agendado'"),
            name="ex_agendamentos_conflito",
        ),
        Index("idx_agendamentos_tenant", "tenant_id"),
        # Alvo da FK composta de handoffs.agendamento_id (ADR 0007)
        UniqueConstraint("tenant_id", "id", name="uq_agendamentos_tenant_id_id"),
        # FK composta: o registro pai precisa ser da mesma clinica (ADR 0007)
        ForeignKeyConstraint(
            ["tenant_id", "profissional_id"],
            ["profissionais.tenant_id", "profissionais.id"],
            name="fk_agendamentos_profissional_id_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "servico_id"],
            ["servicos.tenant_id", "servicos.id"],
            name="fk_agendamentos_servico_id_tenant",
        ),
    )
