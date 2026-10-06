import { Table } from '@mantine/core';
import classes from './DataTablePreview.module.css';

interface DataTablePreviewProps {
  title: string;
  columns: string[];
  rows: unknown[][];
}

function renderCell(value: unknown) {
  // NULL и пустая строка в SQL-заданиях — разные значения, и разница бывает
  // ключом к ответу. Поэтому NULL подписывается явно, а строка берётся в кавычки
  // только если она пустая.
  if (value === null || value === undefined) return <span className={classes.null}>NULL</span>;
  if (value === '') return <span className={classes.null}>''</span>;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
}

export function DataTablePreview({ title, columns, rows }: DataTablePreviewProps) {
  // Числовые колонки выравниваются вправо целиком, вместе с заголовком: так
  // разряды стоят друг под другом и суммы сравниваются на глаз.
  const numeric = columns.map((_, index) =>
    rows.every((row) => row[index] === null || typeof row[index] === 'number'),
  );
  return (
    <figure className={classes.root}>
      <figcaption className={classes.title}>
        <span className={classes.name}>{title}</span>
        <span className={classes.count}>
          {rows.length} × {columns.length}
        </span>
      </figcaption>
      <Table.ScrollContainer minWidth={columns.length * 96} type="native">
        <Table className={classes.table} striped highlightOnHover withRowBorders={false}>
          <Table.Thead>
            <Table.Tr>
              {columns.map((column, index) => (
                <Table.Th key={column} scope="col" data-numeric={numeric[index] || undefined}>
                  {column}
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row, rowIndex) => (
              <Table.Tr key={rowIndex}>
                {row.map((value, cellIndex) => (
                  <Table.Td key={cellIndex} data-numeric={numeric[cellIndex] || undefined}>
                    {renderCell(value)}
                  </Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </figure>
  );
}
