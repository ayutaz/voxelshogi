import { Component, type ReactNode } from 'react';

export class BoardFrame extends Component<{ on2D: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="board3d" role="alert"><p>立体盤を読み込めませんでした。</p><button type="button" onClick={this.props.on2D}>2Dで続ける</button></div>;
    return this.props.children;
  }
}
