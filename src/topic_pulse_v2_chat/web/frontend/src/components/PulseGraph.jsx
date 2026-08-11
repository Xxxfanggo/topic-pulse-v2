import React from 'react';

export default function PulseGraph() {
  return (
    <div className="pulseGraph" aria-hidden="true">
      <span className="node nodeA" />
      <span className="node nodeB" />
      <span className="node nodeC" />
      <span className="line lineOne" />
      <span className="line lineTwo" />
      <span className="line lineThree" />
    </div>
  );
}
