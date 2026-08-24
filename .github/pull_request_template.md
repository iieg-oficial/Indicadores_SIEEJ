Closes #

## Qué cambia

<!-- Una o dos frases. Si necesitas más, quizá el PR deba partirse. -->

## Cómo se verificó

- [ ] `pre-commit run --all-files` — el CI no lo corre, el hook local sí
- [ ] `pytest -m "not integration"`

## Revisión

- [ ] No incluye `.env`, DSN, tokens ni credenciales
- [ ] El campo `sql` no se expone en respuestas, errores ni logs
- [ ] La documentación afectada quedó actualizada
- [ ] Si toca `catalogo/`: revisado por alguien del área temática
