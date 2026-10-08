"""
app/db/models.py
Modelos SQLAlchemy — todas as tabelas
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, JSON, Boolean, 
    UniqueConstraint, Index, ForeignKey, UUID, Time, Float
)
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
    type = Column(String(50), nullable=False)  # PROCESS_INBOUND, SEND_REMINDER
    status = Column(String(20), default='pending')  # pending, processing, done, failed, dead
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
        UniqueConstraint('id', name='uq_mensagens_message_id'),
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