export function SwitchControl({
  checked,
  disabled,
  label,
  onChange,
  text,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: (checked: boolean) => void;
  text: string;
}) {
  return (
    <label
      className="switch-control"
      data-checked={checked}
      data-disabled={disabled ? "true" : "false"}
    >
      <input
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        role="switch"
        type="checkbox"
      />
      <span aria-hidden="true" className="switch-track" />
      <span className="switch-text">{text}</span>
    </label>
  );
}
