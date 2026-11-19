"""Canal CLI do estudo: recebe mensagens pelo terminal e responde pelo terminal.

Implementa a interface Channel. No MVP, WhatsAppClient ocupa o mesmo lugar.

Uso:
    echo "oi" | python -m app.channels.cli --tenant <uuid> --telefone "(11) 90000-0000"

O canal recebe a mensagem, grava em mensagens e enfileira um job
PROCESS_INBOUND_MESSAGE (etapa 3.2). O processamento pelo worker e a etapa 3.3.
"""
import argparse
import sys
import uuid
from typing import Optional

from app.channels.base import Channel, MensagemEntrada
from app.jobs.queue import gravar_e_enfileirar


class CliChannel(Channel):
    """Canal ligado a um fluxo de entrada e um de saida (por padrao, o terminal).

    Fica vinculado a uma clinica (tenant_id) e a um contato, como uma conversa
    de WhatsApp fica vinculada a um numero.
    """

    def __init__(self, tenant_id: str, contato_telefone: str, entrada=None, saida=None):
        self.tenant_id = tenant_id
        self.contato_telefone = contato_telefone
        self.entrada = entrada if entrada is not None else sys.stdin
        self.saida = saida if saida is not None else sys.stdout

    def receive(self) -> Optional[MensagemEntrada]:
        linha = self.entrada.readline()
        if linha == "":
            # Fim da entrada (EOF): nao ha mais mensagens
            return None
        conteudo = linha.rstrip("\n")
        return MensagemEntrada(
            id=uuid.uuid4().hex,
            tenant_id=self.tenant_id,
            contato_telefone=self.contato_telefone,
            conteudo=conteudo,
        )

    def send_text(self, contato_telefone: str, texto: str) -> None:
        print(f"[para {contato_telefone}] {texto}", file=self.saida)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Canal CLI de mensagens (estudo).")
    parser.add_argument("--tenant", required=True, help="tenant_id (UUID) da clinica")
    parser.add_argument("--telefone", required=True, help="telefone do contato")
    args = parser.parse_args(argv)

    canal = CliChannel(tenant_id=args.tenant, contato_telefone=args.telefone)
    while True:
        mensagem = canal.receive()
        if mensagem is None:
            break
        resultado = gravar_e_enfileirar(mensagem)
        if resultado.duplicada:
            canal.send_text(
                mensagem.contato_telefone,
                f"mensagem duplicada ignorada (id {mensagem.id})",
            )
        else:
            canal.send_text(
                mensagem.contato_telefone,
                f"recebido e enfileirado: job {resultado.job_id} (id {mensagem.id})",
            )


if __name__ == "__main__":
    main()
