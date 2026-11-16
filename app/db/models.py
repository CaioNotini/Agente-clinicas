"""
app/db/models.py
Modelos SQLAlchemy — todas as tabelas
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, JSON, Boolean,
    UniqueConstraint, Index, ForeignKey, UUID, Time, Float,
    CheckConstraint, text
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.sql import func
from app.db.base import Base  # Importa de base.py, não de __init__
import uuid


class Clinica(Base):
    __tablename__ = "clinicas"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    nome = Column(String(200), nullable=False)
    email = Column(String(200))
    telefone = Column(String(20))
    telefone_plantao = Column(String(20))
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_clinicas_tenant_id', 'tenant_id'),
    )


class Profissional(Base):
    __tablename__ = "profissionais"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    nome = Column(String(200), nullable=False)
    especialidade = Column(String(200))
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_profissionais_tenant', 'tenant_id'),
    )


class Servico(Base):
    __tablename__ = "servicos"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    nome = Column(String(200), nullable=False)
    duracao_minutos = Column(Integer, default=30)
    preco = Column(Float)
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_servicos_tenant', 'tenant_id'),
    )


class HorarioTrabalho(Base):
    __tablename__ = "horarios_trabalho"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=False)
    dia_semana = Column(Integer)  # 0=seg, 6=dom
    hora_inicio = Column(Time)
    hora_fim = Column(Time)
    ativo = Column(Boolean, default=True)
    criada_em = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_horarios_tenant', 'tenant_id'),
    )


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    type = Column(String(50), nullable=False)  # PROCESS_INBOUND_MESSAGE, SEND_WHATSAPP, SEND_REMINDER, NOTIFY_HANDOFF
    status = Column(String(20), default='pending')  # pending, processing, done, dead
    payload = Column(JSON)
    run_at = Column(DateTime, default=func.now())
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    last_error = Column(String(500))
    locked_at = Column(DateTime)
    locked_by = Column(String(100))
    criada_em = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_jobs_status_run_at', 'status', 'run_at'),
        Index('idx_jobs_tenant', 'tenant_id'),
    )


class Mensagem(Base):
    __tablename__ = "mensagens"
    
    id = Column(String(100), primary_key=True)  # message_id
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    contato_telefone = Column(String(20), nullable=False)
    conteudo = Column(String(4096), nullable=False)
    direcao = Column(String(10))  # 'entrada' ou 'saida'
    criada_em = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_mensagens_tenant_contato', 'tenant_id', 'contato_telefone'),
    )


class Conversa(Base):
    __tablename__ = "conversas"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    contato_telefone = Column(String(20), nullable=False)
    estado_conversa = Column(String(30), default='idle')  # idle, coletando_info, aguardando_confirmacao, escalada, encerrada
    human_mode = Column(Boolean, default=False)
    historico = Column(JSON)
    criada_em = Column(DateTime, server_default=func.now())
    atualizada_em = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'contato_telefone', name='uq_conversas_tenant_contato'),
        Index('idx_conversas_tenant', 'tenant_id'),
    )


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    acao = Column(String(100), nullable=False)
    descricao = Column(String(500))
    dados = Column(JSON)
    criada_em = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_auditoria_tenant_acao', 'tenant_id', 'acao'),
    )


# Regras de agendamento de cada clínica: antecedência e janela de cancelamento
class RegraAgendamento(Base):
    __tablename__ = "regras_agendamento"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    antecedencia_minima_horas = Column(Integer)
    antecedencia_maxima_dias = Column(Integer)
    janela_cancelamento_horas = Column(Integer)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('tenant_id', name='uq_regras_tenant'),
    )


# Relação entre profissionais e os serviços que realizam
class ProfissionalServico(Base):
    __tablename__ = "profissional_servicos"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=False)
    servico_id = Column(Integer, ForeignKey("servicos.id"), nullable=False)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('profissional_id', 'servico_id', name='uq_profissional_servico'),
        Index('idx_profissional_servicos_tenant', 'tenant_id'),
    )


# Contatos de pacientes: dado mínimo, sem prontuário
class PacienteContato(Base):
    __tablename__ = "pacientes_contatos"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    nome = Column(String(200))
    contato_telefone = Column(String(20), nullable=False)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('tenant_id', 'contato_telefone', name='uq_pacientes_tenant_contato'),
        Index('idx_pacientes_contatos_tenant', 'tenant_id'),
    )


# Registro de cada handoff: quem foi avisado, quem assumiu e quando voltou ao bot
class Handoff(Base):
    __tablename__ = "handoffs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    conversa_id = Column(Integer, ForeignKey("conversas.id"), nullable=False)
    motivo = Column(String(50), nullable=False)
    notificado_em = Column(DateTime)
    assumido_por = Column(String(100))
    assumido_em = Column(DateTime)
    devolvido_em = Column(DateTime)
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_handoffs_tenant', 'tenant_id'),
        Index('idx_handoffs_conversa', 'conversa_id'),
    )


# Histórico de consentimentos: uma linha por aceite, sem sobrescrever o anterior
class Consent(Base):
    __tablename__ = "consents"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    contato_telefone = Column(String(20), nullable=False)
    tipo = Column(String(50), nullable=False)
    versao_texto = Column(String(20), nullable=False)
    canal = Column(String(30))
    concedido_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('idx_consents_tenant_contato', 'tenant_id', 'contato_telefone'),
    )


# Pedidos de privacidade do titular (acesso, correção, exclusão, portabilidade)
class PrivacyRequest(Base):
    __tablename__ = "privacy_requests"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    contato_telefone = Column(String(20), nullable=False)
    tipo = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False)
    criada_em = Column(DateTime, server_default=func.now())
    concluida_em = Column(DateTime)

    __table_args__ = (
        Index('idx_privacy_requests_tenant', 'tenant_id'),
    )


# Agendamentos de consultas: profissional, servico, janela de tempo e status.
# inicio e fim sao timestamptz (com fuso, gravados em UTC). As demais tabelas usam
# timestamp sem fuso; esta e a excecao, registrada no ADR 0004 e na arquitetura.
# O conflito de horario e garantido pela constraint EXCLUDE, com a mesma semantica
# da funcao pura de conflito (intervalo semiaberto [inicio, fim)). Ver ADR 0004.
class Agendamento(Base):
    __tablename__ = "agendamentos"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("clinicas.tenant_id"), nullable=False)
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=False)
    servico_id = Column(Integer, ForeignKey("servicos.id"), nullable=False)
    contato_telefone = Column(String(20), nullable=False)
    inicio = Column(DateTime(timezone=True), nullable=False)
    fim = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, server_default="agendado")  # agendado (ativo) | cancelado
    criada_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        # Intervalo valido: fim sempre depois do inicio
        CheckConstraint("fim > inicio", name="ck_agendamentos_intervalo"),
        # Status restrito aos dois valores desta etapa
        CheckConstraint("status IN ('agendado', 'cancelado')", name="ck_agendamentos_status"),
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
    )