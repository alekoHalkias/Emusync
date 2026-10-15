// 4-digit numeric PIN field, digits only. Shared by the Settings modal and Setup.
import React from "react";

type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  value: string;
  onChange: (v: string) => void;
};

export default function PinInput({ value, onChange, ...rest }: Props): React.ReactElement {
  return (
    <input
      type="text"
      inputMode="numeric"
      maxLength={4}
      placeholder="1234"
      {...rest}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))}
    />
  );
}
