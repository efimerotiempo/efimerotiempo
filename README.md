## Planificador de proyectos

Esta aplicación web permite introducir proyectos y planificar automáticamente sus
fases utilizando la disponibilidad de los trabajadores.

### Uso rápido

```bash
pip install flask
python app.py
```

Visita `http://localhost:5000` en tu navegador para ir directamente a la vista
**Completo**, que combina el calendario, los proyectos y el formulario de alta.
Desde el calendario puedes utilizar la barra deslizante situada bajo los filtros para
cambiar la ventana de 14 días entre 2024 y 2026. El botón **HOY** devuelve la
vista al día actual. Junto a él hay dos flechas **<** y **>** para mover la
vista un día hacia la izquierda o la derecha mientras arrastras la barra, que
ahora actualiza el calendario en tiempo real. Puedes filtrar por nombre de
proyecto y cliente desde los dos cuadros de búsqueda.

Los campos de fecha de los distintos formularios aparecen vacíos por defecto.
Puedes introducir las fechas como `dd-mm` o `dd/mm`; si no incluyes el año,
se tomará automáticamente el año en curso.

Todos los proyectos se guardan por defecto en `data/projects.json`. La
aplicación lee este archivo cada vez que se carga la página principal (la vista
**Completo**), de modo que si añades manualmente proyectos ahí también formarán
parte de la planificación. Si quieres conservar los datos en otra ubicación,
define la variable de entorno `EFIMERO_DATA_DIR` con la ruta a tu carpeta antes
de iniciar la aplicación.

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
color violeta. Puedes desplazarte horizontalmente por el calendario
mientras mantienes pulsada la tecla **Shift** y giras la rueda del ratón
sobre la tabla. Las columnas del calendario se ajustan automáticamente al
contenido para que no haya saltos.

En la pestaña **Proyectos** puedes ver las horas de cada fase y seleccionar la
persona asignada desde un desplegable. Cualquier cambio se guarda
automáticamente. Junto a cada proyecto hay un botón rojo con una **X** para
eliminarlo. Al borrar un proyecto se vuelve a calcular la planificación y en la
lista de conflictos aparece un aviso indicando la eliminación y los cambios que
ha producido.
Si se modifica la prioridad de un proyecto también se vuelve a programar y en la
lista de conflictos se añade una nota indicando qué otros proyectos han cambiado
de fechas debido a esa prioridad. La nota muestra el nombre y cliente de cada
proyecto afectado junto con un ✔ verde si ahora llega a su límite o una ❌
roja en caso contrario.
Puedes pulsar sobre el nombre de un proyecto en la lista de conflictos para
que el calendario salte hasta sus tareas y las resalte igual que si hubieras
hecho clic en ellas, incluso aunque estén fuera del rango visible.

Al crear nuevos proyectos, el planificador reparte cada fase al trabajador
disponible con menos carga, de modo que fases idénticas en proyectos
distintos se asignan a personas diferentes para poder avanzar en paralelo
si hay recursos libres.

El trabajador **Unai** solo recibe tareas si se le asignan manualmente en la
lista de proyectos. El planificador automático lo ignora al repartir
fases por defecto.

Al planificar el montaje se respeta el orden en que cada trabajador termina
su proyecto anterior. Un nuevo montaje se coloca justo después del último
montaje programado para ese trabajador y aprovecha las horas libres de ese
mismo día hasta completar su jornada, salvo que la prioridad del nuevo proyecto
sea mayor y deba adelantarse en la cola.

La fase **Pedidos**, realizada por Irene, se indica ahora mediante el campo
**Plazo acopio**. Esta fase abarca desde que termina el dibujo hasta la fecha
de acopio indicada y no se reparte por horas. Irene puede acumular tantos
proyectos como sea necesario dentro de ese margen sin limitación diaria.

Cada proyecto se colorea automáticamente con tonos claros para que el texto
sea legible en todas las vistas. Las tareas en el calendario muestran primero
el nombre del proyecto seguido del cliente y la fase para identificar mejor
cada entrada.

Al crear un proyecto puedes adjuntar una imagen opcional. Esta se guarda en
`static/uploads` y se muestra en el recuadro informativo que aparece al pulsar
una tarea en el calendario.

El día actual aparece destacado con un borde rojo grueso en el calendario. Las
vistas de **Calendario** y **Completo** permiten plegar o desplegar las filas de
cada trabajador pulsando el símbolo situado junto a su nombre. Además, la lista
de proyectos incluye los mismos cuadros de búsqueda por proyecto y cliente que
el calendario, para filtrar rápidamente la información mostrada.
La sección de proyectos en la vista **Completo** puede plegarse o desplegarse
completamente pulsando el botón que aparece junto a su título.

### Vacaciones

Desde la pestaña **Vacaciones** puedes registrar periodos de descanso para
cualquier trabajador seleccionándolo en la lista y especificando las fechas de
inicio y fin. Los días marcados como vacaciones aparecen rellenados en rojo en
el calendario y no admiten asignaciones de tareas.
