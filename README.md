## Planificador de proyectos

Esta aplicación web permite introducir proyectos y planificar automáticamente sus
fases utilizando la disponibilidad de los trabajadores.

### Uso rápido

```bash
pip install flask
python app.py
```

Visita `http://localhost:5000` en tu navegador para visualizar el calendario y
los proyectos. Utiliza la barra deslizante situada bajo los filtros para
cambiar la ventana de 14 días entre 2024 y 2026. El botón **HOY** devuelve la
vista al día actual. Puedes filtrar por nombre de proyecto y cliente desde los
dos cuadros de búsqueda.

La pestaña **Completo** reúne todas las vistas en una sola página. De arriba
abajo se muestran el formulario de alta, el calendario de dos semanas, la lista
de conflictos y finalmente los proyectos. Todo el conjunto cuenta con una barra
de desplazamiento vertical para consultar la información cómodamente. El
calendario muestra el número de semana encima de cada fecha y la barra
deslizante puede moverse con la rueda del ratón manteniendo pulsada la tecla
Shift. Las columnas del calendario se ajustan automáticamente al contenido.

En la pestaña **Proyectos** puedes ver las horas de cada fase y seleccionar la
persona asignada desde un desplegable. Cualquier cambio se guarda
automáticamente. Tanto en la vista de **Calendario** como en **Completo** se
muestra una fila de **Horas** sobre cada trabajador indicando la carga diaria;
los días sin tareas se muestran como "0h" en rojo y los días completos con
"8h" en verde.

Al crear nuevos proyectos, el planificador reparte cada fase al trabajador
disponible con menos carga, de modo que fases idénticas en proyectos
distintos se asignan a personas diferentes para poder avanzar en paralelo
si hay recursos libres.

Cada proyecto se colorea automáticamente con tonos claros para que el texto
sea legible en todas las vistas.
