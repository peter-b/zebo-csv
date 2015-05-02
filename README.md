# Zebo - Making complex lab data capture easy

## How to run zebo:

    python edit_csv.py [CSV_FILE]

If you don't specify a `CSV_FILE` to edit, zebo will prompt you to
choose one.

## Creating a CSV template

* The first line of the CSV file is the header

* Zebo decides how to treat each column based on the column's name:

  * If the column name ends with "=", then it's a "key" column used to
    narrow down data

  * If the column name ends with "?", then it's a "measurement" column
    that can be edited

  Otherwise, the data is displayed but read-only.

