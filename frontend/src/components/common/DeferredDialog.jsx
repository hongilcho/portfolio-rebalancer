import React, { Suspense, useEffect, useState } from 'react';
import { DialogLoading } from './ViewLoading';

// Start loading on the first open, then preserve the dialog's existing state
// across close/reopen, just as an always-mounted dialog would.
export default function DeferredDialog({ isOpen, onClose, children }) {
  const [hasOpened, setHasOpened] = useState(false);
  useEffect(() => {
    if (isOpen) setHasOpened(true);
  }, [isOpen]);

  if (!isOpen && !hasOpened) return null;
  return (
    <Suspense fallback={isOpen ? <DialogLoading onClose={onClose} /> : null}>
      {children}
    </Suspense>
  );
}
