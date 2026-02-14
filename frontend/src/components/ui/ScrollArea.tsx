/** ScrollArea component for scrollable content */

import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

const ScrollArea = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div ref={ref} className={cn('relative', className)} {...props}>
      <div className="h-full w-full overflow-auto [scrollbar-width:thin] [scrollbar-color:rgba(155,155,155,0.5)_transparent]">
        {children}
      </div>
    </div>
  )
);
ScrollArea.displayName = 'ScrollArea';

export { ScrollArea };
