Closes #

## Qué cambia

<!-- Una o dos frases. Si necesitas más, quizá el PR deba partirse. -->

## Cómo se verificó

- [ ] `pre-commit run --all-files`
- [ ] `pytest -m "not integration"`
- [ ] `python -m indicadores_sieej.cli validar`

## Revisión

- [ ] No incluye `.env`, DSN, tokens ni credenciales
- [ ] El campo `sql` no se expone en respuestas, errores ni logs
- [ ] La documentación afectada quedó actualizada
- [ ] Si toca `catalogo/`: revisado por alguien del área temática
