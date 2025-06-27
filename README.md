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

Existe una pestaña **Completo** que combina el calendario, la lista de proyectos
y el formulario de alta en una sola página. El calendario muestra el número de
semana encima de cada fecha y la barra deslizante puede moverse también con la
rueda del ratón.

En la pestaña **Proyectos** puedes ver las horas de cada fase y seleccionar la
persona asignada desde un desplegable. Cualquier cambio se guarda
automáticamente. Tanto en la vista de **Calendario** como en **Completo** se
muestra una fila de **Horas** sobre cada trabajador indicando la carga diaria;
los días sin tareas se muestran como "0h" en rojo y los días completos con
"8h" en verde.
