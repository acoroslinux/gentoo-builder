# Guia de Resolução de Problemas do Portage & Gentoo Modern 🛠️

Este guia documenta os padrões comuns de resolução de dependências no Gentoo Linux e como o **Gentoo Modern / AçorOS** resolve automaticamente conflitos de compilação sem frustração para o utilizador.

---

## 1. Ciclos de Dependências Circulares (*Circular Dependencies*)

### Sintoma
O Portage devolve a mensagem:
`* Error: circular dependencies: (package-A depends on package-B -> package-C -> package-A)`

### Exemplo Real Resolvido
- `net-print/cups` (com `USE="zeroconf"`) ➔ exige `net-dns/avahi`
- `net-dns/avahi` (com `USE="qt6"`) ➔ exige `dev-qt/qtbase[cups]`
- `dev-qt/qtbase` (com `USE="cups"`) ➔ exige `net-print/cups`

### Como Resolver
Quebrar a ligação desnecessária num dos nós intermediários em `/etc/portage/package.use/00-builder-overrides`:
```ini
# Desativar bindings de Qt5/Qt6 no Avahi para quebrar o ciclo com o CUPS e QtBase
net-dns/avahi dbus gtk gtk3 python -qt5 -qt6
```

---

## 2. Restrições Estritas de USE Flags (*REQUIRED_USE unsatisfied*)

### Sintoma
O Portage devolve a mensagem:
`The following REQUIRED_USE flag constraints are unsatisfied: featureA? ( featureB )`

### Exemplo Real Resolvido
No Samba: `ldap? ( ads )` e `ads? ( ldap )`.
Se a flag `ads` for ativada sem a flag `ldap` (ou vice-versa), o ebuild do Samba recusa-se a compilar.

### Como Resolver
No `/etc/portage/package.use/00-builder-overrides`, alinhar ambas as flags em conjunto:
```ini
# Para cliente/servidor de rede desktop limpo sem servidor de domínio Active Directory:
net-fs/samba client server winbind -ads -ldap
```

---

## 3. Pacotes Fora da Árvore Principal (*No ebuilds to satisfy*)

### Sintoma
O Portage devolve a mensagem:
`emerge: there are no ebuilds to satisfy "categoria/pacote"`

### Causa & Solução
Pacotes específicos de overlays de comunidade (ex: X-Apps do Linux Mint como `xed` ou `pix`) não existem na árvore oficial `gentoo`.
Devem ser substituídos pelos pacotes oficiais mantidos no repositório principal:
- `app-editors/xed` ➔ `app-editors/gedit` (ou `mousepad`)
- `media-gfx/pix` ➔ `media-gfx/eog` (ou `viewnior`)

---

## 4. Otimização Automática de RAM na Compilação (*Low Memory Limits*)

Para evitar travamentos de memória RAM em pacotes pesados (`nodejs`, `rust`, `webkit-gtk`, `gcc`):
O sistema atribui dinamicamente limites de threads em `/etc/portage/package.env/00-builder-ram-limits`:
```ini
net-libs/nodejs low-ram-node.conf
dev-lang/rust low-ram.conf
net-libs/webkit-gtk low-ram.conf
sys-devel/gcc low-ram.conf
```
