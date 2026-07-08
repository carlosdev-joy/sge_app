import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { CalendarIcon } from "lucide-react";

interface DateFiltersProps {
  selectedDay?: string;
  selectedMonth?: string;
  selectedYear?: string;
  onDayChange?: (value: string) => void;
  onMonthChange?: (value: string) => void;
  onYearChange?: (value: string) => void;
  showDay?: boolean;
  showMonth?: boolean;
  showYear?: boolean;
}

const DateFilters = ({ 
  selectedDay, 
  selectedMonth, 
  selectedYear,
  onDayChange, 
  onMonthChange, 
  onYearChange,
  showDay = true,
  showMonth = true,
  showYear = true
}: DateFiltersProps) => {
  const days = Array.from({ length: 31 }, (_, i) => (i + 1).toString().padStart(2, '0'));
  const months = [
    { value: '01', label: 'Janeiro' },
    { value: '02', label: 'Fevereiro' },
    { value: '03', label: 'Março' },
    { value: '04', label: 'Abril' },
    { value: '05', label: 'Maio' },
    { value: '06', label: 'Junho' },
    { value: '07', label: 'Julho' },
    { value: '08', label: 'Agosto' },
    { value: '09', label: 'Setembro' },
    { value: '10', label: 'Outubro' },
    { value: '11', label: 'Novembro' },
    { value: '12', label: 'Dezembro' },
  ];
  const years = Array.from({ length: 5 }, (_, i) => (new Date().getFullYear() - i).toString());

  return (
    <div className="flex items-center gap-2 flex-wrap date-filters">
      <CalendarIcon className="h-4 w-4 text-caixa-aqua" />
      {showDay && (
        <Select value={selectedDay} onValueChange={onDayChange}>
          <SelectTrigger className="w-[100px] bg-card/50 border-caixa-aqua/30">
            <SelectValue placeholder="Dia" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            {days.map(day => (
              <SelectItem key={day} value={day}>{day}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {showMonth && (
        <Select value={selectedMonth} onValueChange={onMonthChange}>
          <SelectTrigger className="w-[140px] bg-card/50 border-caixa-aqua/30">
            <SelectValue placeholder="Mês" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            {months.map(month => (
              <SelectItem key={month.value} value={month.value}>{month.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {showYear && (
        <Select value={selectedYear} onValueChange={onYearChange}>
          <SelectTrigger className="w-[120px] bg-card/50 border-caixa-aqua/30">
            <SelectValue placeholder="Ano" />
          </SelectTrigger>
          <SelectContent>
            {years.map(year => (
              <SelectItem key={year} value={year}>{year}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
};

export default DateFilters;
