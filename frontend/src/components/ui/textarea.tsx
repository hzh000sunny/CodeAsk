import type { Ref, TextareaHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export function Textarea({
  className,
  ref,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & {
  ref?: Ref<HTMLTextAreaElement>;
}) {
  return <textarea className={cn("textarea", className)} ref={ref} {...props} />;
}
