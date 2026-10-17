"""Merge: ko'p filial auditi zanjiri (c4_1) va E-Code AI zanjiri (e3f4a5b6c7d8)

Ikkala zanjir bir xil ota migratsiyadan ajralgan edi; bu migratsiya ularni bitta head ga birlashtiradi.
Hech qanday sxema o'zgartirmaydi.

Revision ID: m_merge_filial_ai
Revises: c4_1, e3f4a5b6c7d8
"""
from typing import Sequence, Union

revision: str = 'm_merge_filial_ai'
down_revision: Union[str, Sequence[str], None] = ('c4_1', 'e3f4a5b6c7d8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
