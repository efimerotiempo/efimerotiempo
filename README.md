## Hi there 👋

<!--
**efimerotiempo/efimerotiempo** is a ✨ _special_ ✨ repository because its `README.md` (this file) appears on your GitHub profile.

Here are some ideas to get you started:

- 🔭 I’m currently working on ...
- 🌱 I’m currently learning ...
- 👯 I’m looking to collaborate on ...
- 🤔 I’m looking for help with ...
- 💬 Ask me about ...
- 📫 How to reach me: ...
- 😄 Pronouns: ...
- ⚡ Fun fact: ...
-->

## Kanban con Flask

Este proyecto contiene una pequeña aplicación de ejemplo que implementa un tablero Kanban al estilo Jira usando Flask y SQLite.

### Requisitos

- Python 3
- Las dependencias listadas en `requirements.txt`

### Uso

1. Instala las dependencias: `pip install -r requirements.txt`.
2. Ejecuta la aplicación con `python app.py`.
3. Abre `http://localhost:5000` en tu navegador para ver el tablero.

Puedes arrastrar las tarjetas entre columnas y crear nuevas especificando relaciones de padre e hija.
Al hacer clic sobre una tarjeta se abre un formulario emergente para editar sus datos.
Cada columna está coloreada según su estado por defecto: **Todo**, **Doing**, **Blocked** y **Done**.

