"""Modèles Pydantic (corps de requêtes + thème)."""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

HEX = r"^#[0-9a-fA-F]{6}$"


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


# ------------------------------------------------------------------- thème

class ThemeLink(_Base):
    width: Optional[int] = Field(None, ge=40, le=600)   # None = largeur automatique
    show_icon: bool = True
    show_name: bool = True
    show_description: bool = False
    icon_size: int = Field(16, ge=10, le=64)          # px


class ThemeFonts(_Base):
    link: int = Field(14, ge=8, le=32)                # px
    description: int = Field(11, ge=8, le=32)
    category: int = Field(15, ge=8, le=40)


class ThemeColors(_Base):
    button: str = Field("#1c1e22", pattern=HEX)
    button_hover: str = Field("#464a50", pattern=HEX)
    text: str = Field("#f2f2f2", pattern=HEX)
    button_opacity: float = Field(0.88, ge=0, le=1)
    panel: str = Field("#14181e", pattern=HEX)
    panel_opacity: float = Field(0.45, ge=0, le=1)


class ThemeBackground(_Base):
    mode: Literal["fixed", "random"] = "fixed"
    image: str = ""                                   # fichier de config/fonds ou URL
    attachment: Literal["fixed", "scroll"] = "fixed"


class Theme(_Base):
    columns: int = Field(3, ge=1, le=6)
    link: ThemeLink = ThemeLink()
    fonts: ThemeFonts = ThemeFonts()
    colors: ThemeColors = ThemeColors()
    background: ThemeBackground = ThemeBackground()


# ------------------------------------------------------------------- liens

class LinkStyle(_Base):
    """Surcharges par lien : None = hériter du thème."""
    icon: Optional[str] = None                        # URL ou fichier de config/icons
    show_icon: Optional[bool] = None
    show_name: Optional[bool] = None
    show_description: Optional[bool] = None
    width: Optional[int] = Field(None, ge=0, le=600)  # 0 = automatique
    icon_size: Optional[int] = Field(None, ge=10, le=64)
    font_size: Optional[int] = Field(None, ge=8, le=32)
    color: Optional[str] = Field(None, pattern=HEX)   # fond du bouton
    text: Optional[str] = Field(None, pattern=HEX)    # couleur du texte


class LinkIn(_Base):
    name: str = Field(min_length=1)
    url: str = ""
    description: str = ""
    hidden: bool = False
    style: Optional[LinkStyle] = None


class CategoryIn(_Base):
    name: str = Field(min_length=1)


class CategoryRef(_Base):
    ci: int
    ki: int


class CategoryTarget(_Base):
    ci: int
    index: int


class CategoryMoveIn(_Base):
    source: CategoryRef
    target: CategoryTarget


class LinkRef(_Base):
    ci: int
    ki: int
    li: int


class LinkTarget(_Base):
    ci: int
    ki: int
    index: int


class MoveIn(_Base):
    source: LinkRef
    target: LinkTarget

