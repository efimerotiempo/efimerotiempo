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
vista al día actual. Junto a él hay dos flechas **<** y **>** para mover la
vista un día hacia la izquierda o la derecha mientras arrastras la barra, que
ahora actualiza el calendario en tiempo real. Puedes filtrar por nombre de
proyecto y cliente desde los dos cuadros de búsqueda.

Todos los proyectos se guardan en `data/projects.json`. La aplicación lee este
archivo cada vez que se carga la página principal, de modo que si añades
manualmente proyectos ahí también formarán parte de la planificación.

 También puedes añadir **Hitos** indicando una descripción y una fecha. En ambas
 vistas de calendario aparecerá una línea roja en la fecha del hito y la
 descripción se muestra en horizontal dentro de su celda en color rojo. Existe
 una pestaña **Hitos** que muestra la lista completa y permite eliminarlos con
 una **X** roja.

La pestaña **Completo** reúne todas las vistas en una sola página. En la
parte superior se muestran, de izquierda a derecha, el formulario de alta, el
de hitos y la lista de conflictos. Debajo aparecen el calendario y, al final,
la lista de proyectos. Cada sección se expande por
completo y la página ofrece una barra de desplazamiento vertical para consultar
la información cómodamente sin necesidad de reducir el zoom. El
calendario muestra el número de semana una sola vez por semana, en negrita y
color violeta, y la barra
deslizante puede moverse con la rueda del ratón manteniendo pulsada la tecla
Shift. Las columnas del calendario se ajustan automáticamente al contenido.

En la pestaña **Proyectos** puedes ver las horas de cada fase y seleccionar la
persona asignada desde un desplegable. Cualquier cambio se guarda
automáticamente. Junto a cada proyecto hay un botón rojo con una **X** para
eliminarlo. Al borrar un proyecto se vuelve a calcular la planificación y en la
lista de conflictos aparece un aviso indicando la eliminación y los cambios que
ha producido.

Al crear nuevos proyectos, el planificador reparte cada fase al trabajador
disponible con menos carga, de modo que fases idénticas en proyectos
distintos se asignan a personas diferentes para poder avanzar en paralelo
si hay recursos libres.

La fase **Pedidos**, realizada por Irene, se indica ahora mediante el campo
**Plazo acopio**. Esta fase abarca desde que termina el dibujo hasta la fecha
de acopio indicada y no se reparte por horas. Irene puede acumular tantos
proyectos como sea necesario dentro de ese margen sin limitación diaria.

Cada proyecto se colorea automáticamente con tonos claros para que el texto
sea legible en todas las vistas.
