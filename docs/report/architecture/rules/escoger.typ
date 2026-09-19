== Escoger el valor

Para escoger el valor de entre los distintos propuestos por el parser,
seguiremos un proceso, que también contará con un archivo de configuración:
+ Limpiamos un poco con un trim()
+ Para los campos con un formato regular y que lo soporten, se pasará una serie de tests para eliminar candidatos. Por ejemplo, si el NIF tiene una letra en mayúscula y ocho números, y un valor no cumple estas restricciones, el candidato se rechaza por razón de formato. Otro formato puede ser tener caracteres especiales o no, por ejemplo. Estos tests tendran un ID para poder ser seleccionados desde la configuración por cada _field_
+ Se calculará la puntuación de cada valor, multiplicando la confianza por el peso del extractor (peso configurable). Cada _field_ tendrá un _threshold_ configurable de puntuación que deberá superar para continuar.
+ Se escogerán la puntuación máxima. En caso de ser un único valor, hemos terminado. En caso contrario, se comparan los valores. Si son todos iguales, hemos terminado. Si no, seleccionamos con respecto a un ranking de extractores (configurable por _field_).

